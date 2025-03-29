import re
import json
import urllib.request
import urllib.parse
import html
import random
import time


class YouTubeUnblocker:
    """A custom YouTube parser that bypasses API blocks on Replit"""
    
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 11.5; rv:90.0) Gecko/20100101 Firefox/90.0',
        'Mozilla/5.0 (X11; Linux i686; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 11_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1'
    ]
    
    def __init__(self):
        """Initialize the YouTube unblocker"""
        pass
    
    def _get_random_user_agent(self):
        """Get a random user agent to avoid detection"""
        return random.choice(self.USER_AGENTS)
    
    def _make_request(self, url):
        """Make a request to YouTube with rotating user agents"""
        headers = {
            'User-Agent': self._get_random_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
        }
        
        req = urllib.request.Request(url, headers=headers)
        
        try:
            with urllib.request.urlopen(req) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            print(f"Error making request to {url}: {e}")
            return None
    
    def search_videos(self, query, max_results=5):
        """Search for YouTube videos with a query
        
        Args:
            query (str): The search query
            max_results (int): Maximum number of results to return
            
        Returns:
            list: List of video dictionaries with info
        """
        # Encode the search query
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        
        html_content = self._make_request(url)
        if not html_content:
            return []
        
        # Extract video information using regex
        video_ids = re.findall(r"videoId\":\"(.*?)\"", html_content)
        titles = re.findall(r"title\":{\"runs\":\[{\"text\":\"(.*?)\"}", html_content)
        
        # Combine results and limit to max_results
        results = []
        seen_ids = set()
        
        for i in range(min(len(video_ids), len(titles))):
            video_id = video_ids[i]
            
            # Skip duplicates
            if video_id in seen_ids:
                continue
                
            seen_ids.add(video_id)
            
            title = html.unescape(titles[i])
            results.append({
                'id': video_id,
                'title': title,
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                'source': 'youtube'
            })
            
            if len(results) >= max_results:
                break
                
        return results
    
    def get_video_info(self, video_id):
        """Get detailed information about a video
        
        Args:
            video_id (str): YouTube video ID
            
        Returns:
            dict: Video information dictionary
        """
        url = f"https://www.youtube.com/watch?v={video_id}"
        html_content = self._make_request(url)
        
        if not html_content:
            return None
            
        # Extract video title
        title_match = re.search(r'<title>(.*?) - YouTube</title>', html_content)
        title = html.unescape(title_match.group(1)) if title_match else "Unknown Title"
        
        # Extract video duration (in seconds)
        duration_match = re.search(r'"lengthSeconds":"(\d+)"', html_content)
        duration = int(duration_match.group(1)) if duration_match else 0
        
        # Extract channel name
        channel_match = re.search(r'"ownerChannelName":"(.*?)"', html_content)
        channel = html.unescape(channel_match.group(1)) if channel_match else "Unknown Channel"
        
        # Try to extract streaming URLs (this is more complex and may need additional parsing)
        # For now, we'll just return the basic info
        
        return {
            'id': video_id,
            'title': title,
            'duration': duration,
            'uploader': channel,
            'url': url,
            'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            'source': 'youtube'
        }
    
    def extract_video_id(self, url):
        """Extract video ID from a YouTube URL
        
        Args:
            url (str): YouTube URL
            
        Returns:
            str: Video ID or None if not found
        """
        # YouTube video URL pattern
        youtube_regex = r'(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        
        match = re.search(youtube_regex, url)
        if match:
            return match.group(1)
        return None


class SpotifyUnblocker:
    """A simple fallback for Spotify links using YouTube search"""
    
    def __init__(self, youtube_parser):
        """Initialize with a YouTube parser for fallback searches
        
        Args:
            youtube_parser (YouTubeUnblocker): An instance of the YouTube parser
        """
        self.youtube = youtube_parser
    
    def get_track_info(self, track_url):
        """Extract track info from Spotify URL and search on YouTube
        
        Args:
            track_url (str): Spotify track URL
            
        Returns:
            dict: Track info from YouTube search
        """
        # Extract track name and artist from URL or page content
        track_id = track_url.split('/')[-1].split('?')[0]
        
        try:
            # Make a request to get the track name from Spotify's embed API
            url = f"https://open.spotify.com/embed/track/{track_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
            
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                html_content = response.read().decode('utf-8')
                
                # Extract track name and artist
                title_match = re.search(r'<title>(.*?)</title>', html_content)
                if title_match:
                    # Title format is typically "Track Name - Artist"
                    title = html.unescape(title_match.group(1))
                    search_query = title.replace(" by ", " ")
                else:
                    # Use the track ID as fallback
                    search_query = f"spotify track {track_id}"
        except Exception as e:
            print(f"Error getting Spotify track info: {e}")
            search_query = f"spotify track {track_id}"
        
        # Search YouTube for the track
        search_results = self.youtube.search_videos(search_query, max_results=1)
        
        if search_results:
            return search_results[0]
        
        return None
    
    def get_playlist_tracks(self, playlist_url, max_tracks=10):
        """Get tracks from a Spotify playlist by scraping the embed page
        
        Args:
            playlist_url (str): Spotify playlist URL
            max_tracks (int): Maximum number of tracks to return
            
        Returns:
            list: List of track info dictionaries
        """
        # Extract playlist ID
        playlist_id = playlist_url.split('/')[-1].split('?')[0]
        
        # Results list
        results = []
        
        try:
            # Get the playlist embed page
            url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
            
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                html_content = response.read().decode('utf-8')
                
                # Extract playlist title
                title_match = re.search(r'<title>(.*?)</title>', html_content)
                playlist_title = html.unescape(title_match.group(1)) if title_match else "Spotify Playlist"
                
                # Extract track names and artists
                # This is a simplified approach - real implementation would need more robust parsing
                track_matches = re.findall(r'data-testid="track-row".*?<a.*?>(.*?)</a>.*?<a.*?>(.*?)</a>', html_content, re.DOTALL)
                
                for i, (track_name, artist) in enumerate(track_matches):
                    if i >= max_tracks:
                        break
                        
                    search_query = f"{html.unescape(track_name)} {html.unescape(artist)}"
                    
                    # Search YouTube for this track
                    search_results = self.youtube.search_videos(search_query, max_results=1)
                    
                    if search_results:
                        results.append(search_results[0])
                    
                    # Wait a bit to avoid rate limiting
                    time.sleep(0.5)
        except Exception as e:
            print(f"Error getting Spotify playlist info: {e}")
            
        return {
            'title': playlist_title,
            'tracks': results,
            'source': 'spotify_playlist'
        }


# Testing function for debug
def test_youtube_parser():
    yt = YouTubeUnblocker()
    results = yt.search_videos("never gonna give you up", max_results=3)
    
    print("Search Results:")
    for result in results:
        print(f"Title: {result['title']}")
        print(f"URL: {result['url']}")
        print(f"Thumbnail: {result['thumbnail']}")
        print("---")
    
    if results:
        video_id = yt.extract_video_id(results[0]['url'])
        video_info = yt.get_video_info(video_id)
        
        print("\nVideo Info:")
        print(f"Title: {video_info['title']}")
        print(f"Duration: {video_info['duration']} seconds")
        print(f"Uploader: {video_info['uploader']}")


if __name__ == "__main__":
    test_youtube_parser()