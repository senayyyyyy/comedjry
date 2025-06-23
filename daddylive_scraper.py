import requests
from bs4 import BeautifulSoup
import re
import os

def scrape_daddylive_channels(url="https://daddylive.dad/24-7-channels.php"):
    """
    Scrapes the daddylive.dad website for 24/7 channels, extracts m3u8 stream URLs,
    and returns a list of dictionaries with channel name and stream URL.
    """
    print(f"Fetching main page: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the main page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    channels_data = []

    # The channels are typically within a table or div structure.
    # Let's inspect the page structure. Looking at the page, it seems
    # channels are in a table, and each row contains a link to the player page.

    # Find the table containing the channels.
    # We'll look for `<a>` tags that link to player pages, often identified by 'player.php'
    # or similar patterns in their href attributes.
    # A common pattern is a table where each row has a channel name and a link.

    # More robust way: find all 'a' tags that likely lead to a player page.
    # They seem to be structured as: <a href="player.php?id=...">Channel Name</a>
    # Or embedded in a 'tr' with a 'td'
    
    # Try to find common patterns for channel links
    # The links are typically structured like: player.php?id=CHANNEL_ID
    # And the channel name is the text of the anchor tag.
    
    # Example structure from inspecting the page:
    # <div class="col-lg-2 col-md-3 col-sm-4 col-xs-6" style="margin-bottom:10px;">
    #     <div class="hovereffect">
    #         <a href="player.php?id=903">
    #             <img class="img-responsive" src="..." alt="Channel Name">
    #             <div class="overlay" style="background-color:rgba(215, 230, 246, 0.45)">
    #                 <h2>Channel Name</h2>
    #             </div>
    #         </a>
    #     </div>
    # </div>
    
    # Find all div elements with class 'col-lg-2' which contain the channel links
    channel_divs = soup.find_all('div', class_=re.compile(r'col-lg-2|col-md-3|col-sm-4|col-xs-6'))

    if not channel_divs:
        print("Could not find any channel divs. Check the page structure.")
        return []

    for div in channel_divs:
        link_tag = div.find('a', href=re.compile(r'player\.php\?id=\d+'))
        if link_tag:
            channel_name_h2 = link_tag.find('h2')
            if channel_name_h2:
                channel_name = channel_name_h2.get_text(strip=True)
            else:
                # Fallback if h2 is not found, try getting text directly from link
                channel_name = link_tag.get_text(strip=True)
            
            player_page_path = link_tag['href']
            # Construct absolute URL for the player page
            player_page_url = f"https://daddylive.dad/{player_page_path}"
            
            print(f"  Found channel: {channel_name}, Player URL: {player_page_url}")
            
            m3u8_url = extract_m3u8_from_player_page(player_page_url)
            if m3u8_url:
                channels_data.append({
                    'name': channel_name,
                    'url': m3u8_url
                })
            else:
                print(f"    Could not extract M3U8 for {channel_name}")
    
    return channels_data

def extract_m3u8_from_player_page(player_page_url):
    """
    Fetches the player page and extracts the m3u8 stream URL using regex.
    """
    print(f"    Fetching player page: {player_page_url}")
    try:
        player_response = requests.get(player_page_url, timeout=10)
        player_response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"    Error fetching player page {player_page_url}: {e}")
        return None

    player_html = player_response.text

    # Common patterns for m3u8 URLs in HTML/JS:
    # 1. Inside a <script> tag, as part of a video player configuration (e.g., video.js, jwplayer)
    #    Look for patterns like:
    #    src: "http://example.com/stream.m3u8"
    #    file: "http://example.com/stream.m3u8"
    #    source: { src: "http://example.com/stream.m3u8" }
    # 2. Directly embedded in an iframe's src, but less common for the actual stream.

    # Regex to find .m3u8 URLs
    # This regex is broad and looks for http/https followed by anything ending in .m3u8
    # It also tries to capture URLs within double or single quotes.
    m3u8_pattern = re.compile(r'(https?://[^\s"\']*\.m3u8(?:[^\s"\']*?)?)')
    
    match = m3u8_pattern.search(player_html)
    if match:
        m3u8_url = match.group(1)
        print(f"      Extracted M3U8 URL: {m3u8_url}")
        return m3u8_url
    else:
        print(f"      No M3U8 URL found on player page: {player_page_url}")
        
        # Sometimes, the actual stream is in an iframe on the player page.
        # Let's try to find an iframe and recursively check its content if needed.
        player_soup = BeautifulSoup(player_html, 'html.parser')
        iframe_tag = player_soup.find('iframe')
        if iframe_tag and iframe_tag.get('src'):
            iframe_src = iframe_tag['src']
            print(f"      Found iframe: {iframe_src}")
            # If the iframe src is a relative path, make it absolute.
            if not iframe_src.startswith('http'):
                # Assuming the iframe is on the same domain as the player page
                # Need to handle cases where iframe_src is '/path' or 'path'
                base_url_parts = player_page_url.split('/')
                iframe_src_abs = '/'.join(base_url_parts[:-1]) + '/' + iframe_src.lstrip('/')
                print(f"      Resolved iframe URL: {iframe_src_abs}")
                return extract_m3u8_from_player_page(iframe_src_abs) # Recursive call
            else:
                return extract_m3u8_from_player_page(iframe_src) # Recursive call
        
    return None

def create_m3u_playlist(channels_data, filename="daddylive_247_channels.m3u"):
    """
    Creates an M3U playlist file from the scraped channels data.
    """
    if not channels_data:
        print("No channel data to create a playlist.")
        return

    m3u_content = "#EXTM3U\n"
    for channel in channels_data:
        m3u_content += f'#EXTINF:-1 tvg-name="{channel["name"]}",{channel["name"]}\n'
        m3u_content += f'{channel["url"]}\n'

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        print(f"\nSuccessfully created M3U playlist: {filename}")
        print(f"Playlist saved to: {os.path.abspath(filename)}")
    except IOError as e:
        print(f"Error writing M3U file: {e}")

if __name__ == "__main__":
    print("Starting DaddyLive 24/7 Channels Scraper...")
    channels = scrape_daddylive_channels()
    if channels:
        create_m3u_playlist(channels)
    else:
        print("No channels were scraped. M3U playlist not created.")
    print("Script finished.")
