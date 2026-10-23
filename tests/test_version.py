import importlib.util
import tempfile
import unittest
import shutil
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stamp_version', ROOT / 'scripts/stamp_version.py')
version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version)


class VersionTests(unittest.TestCase):
    def stamp(self, environment, source='<span id="site-version">v20261024-2</span>'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'index.html'
            path.write_text(source)
            result = version.stamp(path, environment)
            return result, path.read_text()

    def test_local_preview_keeps_the_visible_source_version(self):
        value, html = self.stamp({})
        self.assertEqual(value, 'v20261024-2')
        self.assertIn('>v20261024-2</span>', html)

    def test_every_deployment_and_rerun_has_a_unique_version(self):
        environment = {'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_NUMBER': '128', 'GITHUB_RUN_ATTEMPT': '1'}
        first, html = self.stamp(environment)
        self.assertEqual(first, 'v20261024-2+aaaaaaa.128.1')
        self.assertIn(first, html)
        second, _ = self.stamp({**environment, 'GITHUB_RUN_ATTEMPT': '2'}, html)
        third, _ = self.stamp({**environment, 'GITHUB_RUN_NUMBER': '129'}, html)
        self.assertEqual(len({first, second, third}), 3)
        self.assertEqual(second.count('+'), 1)

    def test_malformed_build_data_or_missing_footer_cannot_publish_a_false_version(self):
        for environment in [{'GITHUB_SHA': 'oops'}, {'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_NUMBER': '<script>', 'GITHUB_RUN_ATTEMPT': '1'}]:
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                self.stamp(environment)
        for source in ['', '<span id="site-version">old</span>', '<span id="site-version">v20261024-2</span>' * 2]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.stamp({}, source)

    def test_build_version_also_updates_nested_imports_without_touching_vendored_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            html=root/'index.html'
            html.write_text('<script src="app.js?v=20261024-2"></script><span id="site-version">v20261024-2</span>')
            app=root/'app.js';app.write_text("import './assets/scene.js?v=20261024-2';")
            assets=root/'assets';assets.mkdir()
            scene=assets/'scene.js';scene.write_text("import './motion.js?v=20261024-2';import './three.min.js?v=0.186.1';")
            vendor=assets/'three.min.js';vendor.write_text("// Keep vendored ?v=20261024-2' verbatim")
            environment={'GITHUB_SHA':'b'*40,'GITHUB_RUN_NUMBER':'200','GITHUB_RUN_ATTEMPT':'1'}
            release=version.stamp(html,environment)
            for path in [html,app,scene]:
                self.assertIn('v='+release[1:],path.read_text())
            self.assertIn('three.min.js?v=0.186.1',scene.read_text())
            self.assertEqual(vendor.read_text(),"// Keep vendored ?v=20261024-2' verbatim")
            repeated=version.stamp(html,{**environment,'GITHUB_RUN_ATTEMPT':'2'})
            self.assertIn('v='+repeated[1:],scene.read_text())
            self.assertNotIn(release[1:],scene.read_text())

    def test_workflow_stamps_after_copying_before_upload(self):
        workflow = (ROOT / '.github/workflows/pages.yml').read_text()
        self.assertLess(workflow.index('cp index.html'), workflow.index('scripts/stamp_version.py _site/index.html'))
        self.assertLess(workflow.index('scripts/stamp_version.py _site/index.html'), workflow.index('actions/upload-pages-artifact'))

    def test_actual_public_bundle_has_one_release_version_and_preserves_source(self):
        source_html=(ROOT/'index.html').read_text()
        source_app=(ROOT/'app.js').read_text()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['index.html','app.js','learning.js','i18n.js','styles.css']:
                shutil.copyfile(ROOT/name,root/name)
            shutil.copytree(ROOT/'assets',root/'assets')
            original_engine=(root/'assets/mascot/three.min.js').read_bytes()
            release=version.stamp(root/'index.html',{'GITHUB_SHA':'c'*40,'GITHUB_RUN_NUMBER':'300','GITHUB_RUN_ATTEMPT':'1'})
            for path in [root/'index.html',*root.rglob('*.js')]:
                for value in re.findall(r'[?&]v=(2026[^\x22\x27]+)',path.read_text()):
                    self.assertEqual(value,release[1:])
            self.assertIn(release,(root/'index.html').read_text())
            self.assertEqual((root/'assets/mascot/three.min.js').read_bytes(),original_engine)
        self.assertEqual((ROOT/'index.html').read_text(),source_html)
        self.assertEqual((ROOT/'app.js').read_text(),source_app)
