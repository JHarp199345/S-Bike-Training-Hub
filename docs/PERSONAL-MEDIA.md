# Personal media during rides

Open Ride and use the hamburger menu: choose a view, choose your music or personal Plex video, then choose a saved workout or route. The controls and menu stay consistent across views. Changing scenery keeps the music playing. Entering the video view pauses music, and leaving it pauses video.

## Your music folder

On macOS, open Settings → Music connections on the computer running the Hub and press **Choose folder…** to pick any folder of music (or an empty one). You can drag songs onto the drop zone there to add them. The Hub reads existing files without moving, renaming or changing them. Dragging files onto the upload area adds those files locally without overwriting existing ones. Nothing is uploaded to a music service.

Linux/Windows native folder selection is **in progress** and its unavailable button is disabled. Use **Ride → Playlists → Files from this device**, or configure `HUB_MUSIC_FOLDER` for a folder on the host. Automatic tempo measurement uses macOS audio decoding; other systems can use existing BPM tags, with missing tempo shown as unknown.

The ride screen's **Library** shows the folder as Songs, Albums and Artists, using the titles, artists, albums and cover art already inside the files (mp3, m4a/aac and flac; other formats are named from the file, such as `01. Artist - Title.mp3`). Each song's tempo comes from its BPM tag when it has one; otherwise the Hub measures it once, on this computer.

**Workout Tempo** lists the songs that fit your cadence band. A song fits at its tempo or half of it: 174 BPM is one beat per pedal stroke at 87 rpm, and an 87 BPM song fits too. The band is the one the ride is steering to (your workout's or session's cadence target). Turn on *Keep choosing songs that fit my cadence* and the next song is picked from those that fit. Music never changes the ride; the cadence is only read to suggest songs.

## Connections

| Source | Setup | Current scope |
| --- | --- | --- |
| Your music folder | Choose folder in Music connections (macOS) | Songs, albums, artists, tempo and cadence matching; plays on any paired device. |
| Files from this device | Ride → Playlists → Files from this device | Browser-supported audio; select files again after reload. Files are not uploaded. |
| Apple Music | In progress; unavailable without publisher MusicKit setup | No working connection is promised until setup and live-account checks are complete. |
| Plex music | Connect, approve official sign-in or scan its QR, choose your personal server | In progress: personal music playlists; server must be reachable and live-account playback still needs verification. |
| Plex video | Choose Watch · Plex, then choose video | In progress: personal movies and episodes in browser-playable MP4/WebM containers; real playback verification pending. |

The music folder, local files, queue controls, credential boundaries and range streaming have automated and browser verification. Live Apple Music and Plex accounts and full end-to-end Plex video playback have not yet been verified. A supported container alone does not ensure the browser supports its codecs. Files requiring transcoding, subtitles, and Plex's licensed streaming catalog use Plex's own player. Plex subscriptions, licensing, and remote playback restrictions remain governed by Plex.

iBroadcast and OpenSubsonic connection setup are **in progress** and are not offered as working integrations in this release.

## Publisher setup

Athletes do not need developer accounts. The app publisher supplies a valid signed Apple Music developer token: for this local development build, enter it in the collapsed publisher section in Music connections, or provide `HUB_APPLE_MUSIC_DEVELOPER_TOKEN` in the environment. Apple tokens expire and must be refreshed by the publisher. This build has no hosted token-renewal service. See Apple's official [MusicKit](https://developer.apple.com/musickit/) setup.

## Privacy

The chosen folder and what the Hub learns about it (titles, cover art, tempo) are kept in `music_library.json` and `music_cache/` next to the app. Both are excluded from Git and the MCP bundle, along with common audio file types. The Hub stores Plex access in `music.json` beside your athlete data, with owner-only permissions where supported; it is excluded from Git and the MCP bundle too. Music connections and media metadata are not sent to the coaching assistant or recorded as workouts. Apple authorization is managed by the official MusicKit SDK in your browser.

Account and folder setup is limited to the computer running the Hub; paired devices cannot read or change music credentials or the folder. The Hub sends Plex only the account authentication and library or playback requests it needs. Proxied audio/video uses opaque local URLs rather than exposing service credentials in browser URLs. Apple Music playback uses Apple's official player. These services may keep their own listening history and account records under their policies.

Disconnect removes the Hub's saved service access and invalidates its playback URLs. It does not delete the service account or its listening history. Use the service's account controls to revoke authorization there as well.

Use personal media you have the rights to access. Review [Plex terms and privacy](https://www.plex.tv/about/privacy-legal/) and [Apple privacy](https://www.apple.com/legal/privacy/). This project is independent of those providers and is not endorsed by them.
