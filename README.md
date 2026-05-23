# Dual Subtitle Studio

This prototype gives you the first product slice for a dual-language subtitle platform:

- a frontend for video upload, subtitle upload, or link intake
- explicit original language plus two target languages
- a layout preview with safe area padding and stacked subtitle lanes
- a Python API that can process subtitle uploads now and use offline or provider-backed transcription and translation when configured

## Why the transcript comes first

Yes, the system needs a timed transcript first. The clean data model is:

1. ingest source media or an external link
2. extract captions or run speech-to-text with timestamps
3. normalize that result into subtitle cues with `start_ms`, `end_ms`, and `original_text`
4. translate each cue into `target_language_a` and `target_language_b`
5. render the two translated lanes with padding, wrapping, and collision rules
6. stream the overlay in a browser player or export subtitle files and burned-in video

## Folder layout

- [index.html](index.html)
- [styles.css](styles.css)
- [app.js](app.js)
- [api/server.py](api/server.py)
- [requirements.txt](requirements.txt)
- [vercel.json](vercel.json)

## Suggested production architecture

### Frontend

- Use a browser player that can render two subtitle overlays at once.
- Keep lane A and lane B in separate positioned containers.
- Apply safe area padding from the bottom edge and a fixed gap between tracks.
- Prefer WebVTT or ASS for rich styling and runtime subtitle control.

### Backend

- FastAPI app for upload intake, job creation, and status polling
- subtitle parsing for SRT and VTT uploads
- offline transcription via `faster-whisper` when the local AI pack is installed
- offline cue translation via `Argos Translate` when the local AI pack is installed
- provider-backed transcription via OpenAI audio transcription when `OPENAI_API_KEY` is configured
- provider-backed cue translation via OpenAI Responses API when `OPENAI_API_KEY` is configured
- generated overlay payloads plus VTT, SRT, and ASS subtitle artifacts
- optional `ffmpeg` burn-in when `FFMPEG_BINARY` is available

### Models

- Speech-to-text model for timestamped transcript generation
- Translation model or LLM for cue-by-cue translation into two targets
- Optional subtitle post-processing model for better line breaks and reading speed

### Current source support

- Uploaded `SRT` and `VTT` files are processed directly right now.
- Uploaded media can be transcribed when the file format is supported by the provider API and `OPENAI_API_KEY` is present.
- Public direct subtitle URLs can be fetched and processed from the link flow.
- YouTube, Netflix, Hulu, and Prime extraction still need a dedicated ingest worker or browser companion flow.

## Environment variables

Create a local env file from [.env.example](.env.example).

- `OPENAI_API_KEY`
  Optional. Enables cloud transcription and cloud translation.
- `OPENAI_TEXT_MODEL`
  Defaults to `gpt-4.1`.
- `OPENAI_TRANSCRIPTION_MODEL`
  Defaults to `whisper-1` so segment timestamps can be requested.
- `TRANSLATION_QUALITY_MODE`
  Defaults to `contextual_natural`. Provider-backed AI translation uses neighboring subtitle cues as scene context and prioritizes situational accuracy, tone, formality, idioms, and natural target-language phrasing over literal word-for-word translation.
- `ALLOW_DEMO_TRANSLATION`
  Defaults to `0`. Set it to `1` only if you want placeholder preview subtitles instead of a hard error when real transcription and translation are not configured.
- `JOB_PROCESSING_MODE`
  Optional. Use `inline` for serverless deployments so `/api/jobs/submit` returns a completed job in the same request. Use `background` for local threaded processing. On Vercel this defaults to inline automatically.
- `FFMPEG_BINARY`
  Optional path or binary name for burned-in video export.
- `LOCAL_WHISPER_MODEL`
  Defaults to `small` for the offline Whisper model.
- `LOCAL_WHISPER_DEVICE`
  Defaults to `cpu`.
- `LOCAL_WHISPER_COMPUTE_TYPE`
  Defaults to `int8`.
- `LOCAL_TRANSLATION_PIVOT`
  Defaults to `en` for offline translation package planning.

## Hosted backend instead of your PC

The frontend can call a hosted API, so translation and video processing do not need to run on this laptop.

- Leave [api-config.js](api-config.js) blank when the frontend and backend are deployed together and `/api` is same-origin.
- Set `window.DUAL_SUBTITLE_API_BASE` in [api-config.js](api-config.js) when the backend is hosted somewhere else:
  `window.DUAL_SUBTITLE_API_BASE = "https://your-hosted-backend.example.com";`
- For quick testing, open the frontend with `?api=https://your-hosted-backend.example.com`. The app stores that hosted API URL in browser local storage.
- Use an `https://` backend URL for the deployed Vercel frontend so browser security does not block API calls.

For heavier video work, the best setup is usually Vercel for the static frontend and a container backend such as Google Cloud Run, Render, Railway, or Fly.io for transcription, contextual translation, and optional video rendering. The backend host should hold `OPENAI_API_KEY` or another provider key, plus any worker/storage settings.

The included [Dockerfile](Dockerfile) runs the FastAPI backend with `ffmpeg` installed and `JOB_PROCESSING_MODE=inline`, which is the simplest hosted mode for the current in-memory job model. After deploying the container, put the public backend URL in [api-config.js](api-config.js).

## Local offline setup

If you want the app to work without an OpenAI key:

1. Run [setup-local-ai.bat](setup-local-ai.bat)
2. Wait for it to install the offline speech and translation packages
3. Let it download the local Whisper model and Argos language packs
4. Restart [start-local.bat](start-local.bat)
5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

Notes:

- The default local setup installs the app language pack through English as a pivot language so the UI language list stays usable offline.
- The first local setup can take a while because it downloads speech and translation models.
- Simplified and Traditional Chinese are kept distinct by running local OpenCC conversion after offline translation.

## Running locally later

The frontend is static, and the backend expects FastAPI dependencies.

1. Install Python dependencies:
   `pip install -r requirements.txt`
2. Start the API:
   `uvicorn api.server:app --reload`
3. Serve the static files from this folder with any static server, or deploy the folder to Vercel.

## What the current build does

- sends the page form to `POST /api/jobs/submit`
- processes jobs inline on Vercel so the playable cue data returns reliably from the same function invocation
- parses uploaded subtitle files into timed cues
- transcribes uploaded media with local Whisper when the offline stack is installed
- translates each cue into two target languages with local Argos models when the offline stack is installed
- can still use OpenAI as a cloud fallback when `OPENAI_API_KEY` is configured
- uses contextual subtitle-localization instructions with AI providers so translations are based on surrounding cues, situation, tone, and naturalness instead of literal text alone
- generates VTT, SRT, ASS, and overlay JSON artifacts for download
- lets the browser play the uploaded video with generated subtitle overlays when a burned-in video is not available
- keeps lane separation explicit with safe-area and gap settings

## Remaining product work

- add a real ingest worker for YouTube and DRM-limited streaming sources
- move artifact persistence to object storage for production hosting
- add a browser player that consumes the overlay JSON during playback

## Translation quality notes

For the highest naturalness and situational accuracy, use an AI/LLM translation provider. The OpenAI path sends neighboring cues as context and asks for subtitle localization rather than literal translation. Free/offline engines such as Argos Translate or self-hosted LibreTranslate are useful fallbacks, but they are more phrase-by-phrase and usually cannot infer scene tone, relationship dynamics, jokes, sarcasm, or cultural phrasing as reliably.
