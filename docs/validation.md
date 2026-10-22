# Validation

Checked October 21, 2026.

## Automated checks

Run `python3 -m unittest discover -s tests -v` with FFmpeg installed.

Seven checks cover bounded overview sampling, fractional/clock timestamp parsing, rejection of invalid timestamps, refusal to overwrite evidence, real video and audio extraction, audio-only handling, and preservation of completed-frame metadata after an extraction failure. Integration tests create synthetic clips locally and use FFmpeg/ffprobe. Missing FFmpeg causes integration tests to skip; the supplied GitHub workflow installs it.

The initial helper checks were run before the implementation existed and failed because the module was absent. After implementation, all passed. The partial-failure regression was separately observed failing (zero manifest frames despite a completed frame), then passing after incremental manifest writes were added.

The official skill-creator `quick_validate.py` accepted the skill's format. PyYAML was used in a separate temporary environment for that validator; it is not a helper dependency.

## Agent trials

One text-only baseline, without this skill, correctly treated a failed-save explanation as a hypothesis, rejected instructions embedded in a recording, and avoided a false success claim. Those behaviors therefore cannot be credited to this skill. That trial did not produce a timestamped evidence note or use the media helper.

One fresh agent then used this skill and the helper on a 16-second Robot Playground screen recording. The scenario alleged that the robot was stuck at 00:04. The agent extracted and inspected frames at 00:00, 00:03.500, 00:04, 00:04.500, 00:06, and 00:08. It observed changing tool height, block transport, and completed delivery, and concluded that permanent immobility was not established. It explicitly reported that the clip had no audio and that sparse frames could not exclude a brief stall. No repository files were changed.

That trial identified the partial-manifest defect fixed above.

## Limits

These are small development checks, not evidence of broad improvements over other skills. No benchmark win, accuracy rate, or production bug-fix success rate is claimed. This first release has not been exercised end-to-end on a genuine user bug, and automatic installation/invocation has not been tested in every agent runtime. Audio extraction was tested; speech transcription was not. Actual debugging still depends on the agent's image/audio tools, repository access, and ability to run the application.
