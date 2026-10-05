# Personal media during rides

Open Ride and use the hamburger menu: choose a view, choose your music or personal Plex video, then choose a saved workout or route. The controls and menu stay consistent across views. Music plays independently of cadence, power, and scenery; changing scenery preserves music playback. Entering the video view pauses music, and leaving it pauses video.

## Connections

Open Settings → Music connections on the computer running the Hub.

| Source | Setup | Current scope |
| --- | --- | --- |
| Local audio | Choose files in Ride → Playlists | Browser-supported audio; select files again after reload. Files are not uploaded. |
| Plex music | Connect, approve official sign-in or scan its QR, choose your personal server | Personal music playlists; server must be reachable. |
| OpenSubsonic | Enter your server and its API key, or username and password | Personal playlists on compatible servers such as Navidrome. |
| iBroadcast | Connect, approve official device sign-in or scan its QR | Personal cloud music library; publisher registration must be configured first. |
| Apple Music | Connect using Apple's official MusicKit sign-in | Subscriber playlists; publisher token must be configured first. No custom QR sign-in is supplied. |
| Plex video | Choose Watch · Plex, then choose video | Personal movies and episodes in browser-playable MP4/WebM containers. |

These integrations are under development. Local audio playback, queue controls, service contract fixtures, credential boundaries, and range streaming have automated or browser verification. Live accounts for the four services and full end-to-end Plex video playback have not yet been verified. A supported container alone does not ensure the browser supports its codecs. Files requiring transcoding, subtitles, and Plex's licensed streaming catalog use Plex's own player. Plex subscriptions, licensing, and remote playback restrictions remain governed by Plex.

## Publisher setup

Athletes do not need developer accounts. The app publisher supplies an iBroadcast client ID and a valid signed Apple Music developer token. For this local development build, enter them in the collapsed publisher section in Music connections, or provide `HUB_IBROADCAST_CLIENT_ID` and `HUB_APPLE_MUSIC_DEVELOPER_TOKEN` in the environment. Apple tokens expire and must be refreshed by the publisher. This build has no hosted token-renewal service.

Use Apple's official [MusicKit](https://developer.apple.com/musickit/) setup and iBroadcast's [developer authentication](https://help.ibroadcast.com/en/developer/authentication) instructions. OpenSubsonic is a separate protocol, not an adapter for Apple Music, Plex, or iBroadcast.

## Privacy

The Hub stores Plex, iBroadcast, and OpenSubsonic access in `music.json` beside your athlete data, with owner-only permissions where supported. This file and its temporary replacement are excluded from Git. They are not part of the MCP bundle. Music connections and media metadata are not sent to the coaching assistant or recorded as workouts. Apple authorization is managed by the official MusicKit SDK in your browser.

Account setup is limited to the computer running the Hub; paired devices cannot read or change music credentials. The Hub sends the chosen service only the account authentication and library or playback requests needed for that service. Proxied audio/video uses opaque local URLs rather than exposing service credentials in browser URLs. iBroadcast receives play/skip history. Apple Music playback uses Apple's official player. These services may keep their own listening history and account records under their policies.

Disconnect removes the Hub's saved service access and invalidates its playback URLs. It does not delete the service account or its listening history. Use the service's account controls to revoke authorization there as well. Local audio stays in the browser and is not copied into the Hub library.

Use personal media you have the rights to access. Review [Plex terms and privacy](https://www.plex.tv/about/privacy-legal/), [iBroadcast terms](https://www.ibroadcast.com/terms), and [Apple privacy](https://www.apple.com/legal/privacy/). This project is independent of those providers and is not endorsed by them.
