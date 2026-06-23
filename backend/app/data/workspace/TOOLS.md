# TOOLS.md — Local Environment Notes

Skills define _how_ tools work (see
`~/.gundam-halo/skills/<name>/SKILL.md`, loaded by Sprint 36 Tier
2). This file is for **your** specifics — environment notes
unique to this Mac / this user's setup.

## What Goes Here

Things like:

- Camera names and locations (if you wire up a Vision pipeline)
- SSH hosts and aliases (if you want the agent to ssh into a
  remote box)
- Preferred voices for TTS (per user, not per system default)
- Speaker/room names (if you have multiple AirPlay targets)
- Device nicknames (the iPad, the Apple TV in the living room)
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle, Hikvision
- front-door → Entrance, motion-triggered, Reolink

### SSH

- home-server → 192.168.1.100, user: kencheng
- work-laptop → ssh kencheng@work.local

### TTS

- Preferred voice: zh-HK-HiuMaanNeural (default already — see
  VoiceConfig.tts.voice in app/core/config.py)
- Test sentence: 你好 Unicorn，今日天氣點？

### Devices

- ipad → Ken's iPad Pro, sidecar display
- apple-tv-living → Apple TV 4K, living room

### Audio routing

- Input: MacBook Pro microphone (16 kHz mono int16 — see
  voice pipeline sample_rate)
- Output: MacBook Pro speakers OR AirPods Pro (last connected)
- Voice-call output: defaults to MacBook speakers; override with
  AirPlay target via `SetDefaultPlaybackDevice`
```

## Why Separate?

Skills are shared across installs (one per Gundam Halo deployment
on the same machine — e.g. if you ever run a second instance for
testing). Your local notes are yours. Keeping them apart means:

- Skill updates via `git pull` (when the user has forked the
  Gundam Halo repo) don't wipe your environment notes
- You can commit skills to git but keep TOOLS.md out of git
  (it's in `~/.gundam-halo/workspace/` which is per-machine, not
  in the repo)

---

Add whatever helps you do your job. This is your cheat sheet.