select track_id as track_key, track_name, album_title, artist_name, genre, media_type,
       round(duration_ms / 60000.0, 2) as duration_minutes
from {{ ref('stg_tracks') }}
