import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/watch-and-fix/scripts/prepare_media.py'

class MediaTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('prepare_media', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_sampling_is_bounded_and_covers_clip(self):
        sample = self.module().sample_times(600, 12)
        self.assertEqual(len(sample), 12)
        self.assertEqual(sample[0], 0)
        self.assertLess(sample[-1], 600)
        self.assertGreater(sample[-1], 590)
        self.assertEqual(sample, sorted(set(sample)))

    def test_explicit_timestamps_preserve_fractional_seconds(self):
        sample = self.module().parse_times('00:03.250,6,00:01:02.5', 70)
        self.assertEqual(sample, [3.25, 6.0, 62.5])

    def test_out_of_range_and_nonfinite_inputs_fail(self):
        m = self.module()
        for value in ['nan','inf','-1','99','1:60','']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.parse_times(value, 20)

    def test_output_directory_is_never_overwritten(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / 'evidence'
            out.mkdir()
            (out/'notes.txt').write_text('private notes')
            with self.assertRaises(FileExistsError):
                m.new_output(out)
            self.assertEqual((out/'notes.txt').read_text(), 'private notes')


class MediaIntegrationTests(unittest.TestCase):
    def test_extracts_actual_frames_audio_and_manifest(self):
        import json
        import shutil
        import subprocess
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('FFmpeg required for integration test')
        module = MediaTests().module()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            clip = root/'clip with spaces.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=160x120:rate=10:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','mpeg4','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(clip)], check=True)
            out = root/'evidence'
            module.prepare(clip, out, at='0,0.5,1.5', audio=True)
            manifest = json.loads((out/'manifest.json').read_text())
            self.assertEqual([f['seconds'] for f in manifest['frames']], [0,0.5,1.5])
            self.assertTrue(all((out/f['file']).stat().st_size > 100 for f in manifest['frames']))
            self.assertGreater((out/'audio.wav').stat().st_size, 1000)
            audio = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out/'audio.wav')]))['streams'][0]
            self.assertEqual(audio['channels'], 1)
            self.assertEqual(audio['sample_rate'], '16000')

    def test_audio_only_has_no_invented_video_frames(self):
        import shutil
        import subprocess
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('FFmpeg required for integration test')
        module = MediaTests().module()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            clip = root/'note.wav'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=220:duration=1',str(clip)], check=True)
            manifest = module.prepare(clip, root/'out', audio=True)
            self.assertFalse(manifest['video'])
            self.assertEqual(manifest['frames'], [])
            self.assertEqual(manifest['audio_file'], 'audio.wav')

    def test_partial_failure_keeps_completed_frames_in_manifest(self):
        import json
        import subprocess
        from unittest.mock import patch
        import shutil
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('FFmpeg required for integration test')
        module = MediaTests().module()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            clip = root/'clip.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=160x120:rate=10:duration=2','-c:v','mpeg4',str(clip)], check=True)
            original = module.run
            def fail_second_frame(command):
                if command[-1].endswith('frame-001-1.000s.jpg'):
                    raise RuntimeError('simulated decoder failure')
                return original(command)
            out = root/'out'
            with patch.object(module, 'run', side_effect=fail_second_frame):
                with self.assertRaises(RuntimeError):
                    module.prepare(clip, out, at='0,1')
            manifest = json.loads((out/'manifest.json').read_text())
            self.assertEqual(len(manifest['frames']), 1)
            self.assertTrue((out/manifest['frames'][0]['file']).is_file())

if __name__ == '__main__': unittest.main()
