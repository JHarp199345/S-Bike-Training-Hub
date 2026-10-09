# Personal media during rides

Your audio and video live in one private folder on your computer. The Hub reads it and plays it during rides; it never moves, changes or uploads your files, and nothing is sent to any service.

## Your folder

Open **Settings → Music connections** on the computer running the Hub and press **Choose folder…** (macOS) to pick any folder, or an empty one to drop files into. On Linux and Windows, set the `HUB_MUSIC_FOLDER` environment variable to the folder instead. Drag audio or video files onto the upload area to copy them into the folder; existing files are never overwritten.

The library accepts these file formats. Playback depends on the browser and codec; listing a file does not guarantee it can play. The Hub does not transcode files:

| Kind | Formats |
| --- | --- |
| Audio | mp3, m4a/aac, flac, wav, aiff, ogg/opus |
| Video | mp4, m4v, webm, mov (browser-playable; H.264 mp4 is the safest) |

Song titles, artists, albums and cover art come from the tags inside the files (mp3, m4a/aac, flac), or from the file name, such as `01. Artist - Title.mp3`. Each song's tempo comes from its BPM tag when present; otherwise the Hub measures it once, on this computer (macOS).

## On the Ride screen

- **Library** (the library icon on the player bar): a search bar, an **Audio | Video** switch and **36 random picks** from your folder. **New picks** deals another 36, and **Shuffle all** plays every song at random. Choosing a song plays it; choosing a video opens the **Watch** view and plays it there.
- **Choose video** on the Watch view opens the Library on Video.
- **Play files from this device** plays audio or video chosen on the device you're riding with (it stays in that browser).
- The player shows each song's tempo and how it fits your cadence band (174 BPM is one beat per pedal stroke at 87 rpm). Music never changes the workout, resistance or targets.

Changing scenery keeps music playing. Entering the Watch view pauses music, and leaving it pauses the video.

## Privacy

The chosen folder and what the Hub learns about it (titles, cover art, tempo) are kept in `music_library.json` and `music_cache/` next to the app. Both are excluded from Git and the MCP bundle, along with common audio and video file types. Choosing the folder, uploading and rescanning work only on the computer running the Hub; paired phones and tablets can play your media but cannot change the folder. Media details are not sent to the coaching assistant or recorded as workouts.

Use media you have the rights to.

## In progress

Format testing and richer metadata browsing are ongoing. Planned: 16 feature-film recommendations and 32 music-video recommendations, with filters for genre, director and involved artists. Current playback/library features are described above; those category-specific layouts and filters are not yet implemented.
