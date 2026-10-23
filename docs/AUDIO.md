# Intro audio investigation

The reported symptom is opening-song stuttering/crackling. An offline private
check fed 6,997 original Vorbis packets through the exact production adapter
functions: 6,230,720 stereo frames matched an independent FFmpeg decode in
sample count, with every PCM16 value within two least-significant bits.
The inspected iPad intro run reported no AudioUnit underruns. These checks
do not establish correct playback timing or explain the physical symptom.

The original 13.0.5 SDK distinguishes `Buffer::Base()` from `Buffer::Data()`:
Data adds the previous range offset. PCM output previously wrote to Data and
then reported a range starting at zero. A nonzero reused range could therefore
shift the reported data and overwrite trailing storage. Output now writes to
Base through SDK callbacks, checks Capacity, and publishes the matching range.
Refused copies return an empty range.

`t_movie_audio_output.c` exercises the production callbacks with 137 prior
offsets, repeated reuse, empty/oversized output and canaries, including
AddressSanitizer/UndefinedBehaviorSanitizer. A negative control reproduces
corruption with the previous Data callback. This proves the buffer defect and
correction; the causal link to the user's crackle remains unverified. Bounded
PCM output logs include decoder, capacity and prior offset for device testing.

`Documents/log.txt` also records decoder output and audio callback/underrun
counts. Optional `DM_AUDIO_DUMP` names a private raw PCM file at the final
AudioOut append boundary; there is no default path. It contains PCM16, 48 kHz;
use the channel count from its matching OpenAudioOut log. Enable only for a
bounded diagnostic run after saving/closing the game. Never publish derived
audio, packets, disassembly, saves or private device logs.
