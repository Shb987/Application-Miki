import re
import os
from googleapiclient.discovery import build
from app.core.settings import settings
from typing import List, Tuple, Optional

class YouTubeService:
    def __init__(self):
        self.api_key = settings.YOUTUBE_API_KEY or ""
        self.youtube = build('youtube', 'v3', developerKey=self.api_key) if self.api_key else None

    def extract_id(self, input_str: str) -> Tuple[str, str]:
        """
        Extracts Channel ID or Playlist ID from a URL or returns the ID if already provided.
        """
        # Playlist Link: https://www.youtube.com/playlist?list=PL...
        playlist_match = re.search(r"list=([a-zA-Z0-9_-]+)", input_str)
        if playlist_match:
            return playlist_match.group(1), "playlist"

        # Channel Link: https://www.youtube.com/channel/UC...
        channel_match = re.search(r"channel/(UC[a-zA-Z0-9_-]+)", input_str)
        if channel_match:
            return channel_match.group(1), "channel"
        
        # Handle @username: https://www.youtube.com/@username
        handle_match = re.search(r"youtube\.com/(@[a-zA-Z0-9._-]+)", input_str)
        if handle_match:
            return self.get_channel_id_from_handle(handle_match.group(1)), "channel"

        # If it looks like an ID already
        if input_str.startswith("UC"):
            return input_str, "channel"
        if input_str.startswith("PL") or input_str.startswith("UU"):
            return input_str, "playlist"

        return input_str, "text"

    def _check_client(self):
        if not self.youtube:
            raise ValueError("YOUTUBE_API_KEY is not configured in environment settings.")

    def get_channel_id_from_handle(self, handle: str) -> str:
        """Resolves a @handle to a Channel ID."""
        self._check_client()
        request = self.youtube.search().list(
            part="snippet",
            q=handle,
            type="channel",
            maxResults=1
        )
        response = request.execute()
        if not response.get('items'):
            raise ValueError(f"Could not find channel for handle: {handle}")
        return response['items'][0]['id']['channelId']

    def get_uploads_id(self, channel_id: str) -> str:
        """Convert Channel ID to Uploads Playlist ID."""
        request = self.youtube.channels().list(
            part="contentDetails",
            id=channel_id
        )
        response = request.execute()
        if not response.get('items'):
            raise ValueError(f"Channel not found: {channel_id}")
        return response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    def search_playlist_by_name(self, playlist_name: str, channel_id: Optional[str] = None) -> Tuple[str, str]:
        """Search for a playlist ID. If channel_id is provided, limit search to that channel."""
        search_params = {
            "part": "snippet",
            "q": playlist_name,
            "type": "playlist",
            "maxResults": 1
        }
        if channel_id:
            search_params["channelId"] = channel_id

        search_request = self.youtube.search().list(**search_params)
        response = search_request.execute()
        
        if not response.get('items'):
            raise ValueError(f"No playlist found matching '{playlist_name}'" + (f" in channel {channel_id}" if channel_id else ""))
        
        item = response['items'][0]
        return item['id']['playlistId'], item['snippet']['title']

    def fetch_videos(self, playlist_id: str) -> List[dict]:
        """Get all videos from a playlist."""
        videos = []
        request = self.youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50
        )

        while request:
            response = request.execute()
            for item in response['items']:
                title = item['snippet']['title']
                video_id = item['snippet']['resourceId']['videoId']
                published = item['snippet']['publishedAt']
                link = f"https://youtube.com/watch?v={video_id}"
                videos.append({
                    "title": title,
                    "published_at": published,
                    "link": link
                })
            
            request = self.youtube.playlistItems().list_next(request, response)
        
        return videos

youtube_service = YouTubeService()
