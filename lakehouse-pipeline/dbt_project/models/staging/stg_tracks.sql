select
    cast(track_id as integer)                           as track_id,
    trim(track_name)                                    as track_name,
    trim(album_title)                                   as album_title,
    trim(artist_name)                                   as artist_name,
    coalesce(nullif(trim(genre), ''), 'Unknown')        as genre,
    trim(media_type)                                    as media_type,
    -- duration arrives either as milliseconds ("343719") or "m:ss" ("5:43")
    case
        when duration like '%:%' then
            (cast(split_part(duration, ':', 1) as integer) * 60 + cast(split_part(duration, ':', 2) as integer)) * 1000
        else try_cast(duration as bigint)
    end                                                 as duration_ms,
    {{ parse_money('unit_price') }}                     as unit_price
from {{ source('raw', 'tracks') }}
