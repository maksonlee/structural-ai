"""Repository/input tests, not a validation of OpenSees or structural safety."""
from pathlib import Path
import ast
import csv
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
import yaml
from structural_ai.cli import load_project, validate, main, analyze_project, received_scheme
from structural_ai.ifc_reader import Model, parse, encode, Ref, Typed
from structural_ai.provenance import RUNS_RELATIVE, make_run, finish_run, file_hash, inventory, verify_build_inputs

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'project'


class RepositoryTests(unittest.TestCase):
    def test_no_duplicate_workspaces(self):
        for name in ('baseline', 'work', 'old', 'legacy', 'projects', 'artifacts'):
            self.assertFalse((ROOT / name).exists(), name)

    def test_no_custom_solver_in_mainline(self):
        banned = {'linear_fem.py', 'run_analysis.py', 'sensitivity.py'}
        self.assertFalse(banned.intersection(p.name for p in (ROOT / 'src').rglob('*.py')))
        self.assertNotIn('scipy', (ROOT / 'pyproject.toml').read_text().lower())

    def test_only_one_authoritative_ifc(self):
        directory, project, source, config, _ = load_project(PROJECT)
        received=received_scheme(directory,project)
        # One active field owner; an explicitly registered immutable received
        # source supports deterministic revision without a second editable master.
        self.assertEqual(set((PROJECT/'structural/inputs').rglob('*.ifc')),{source,received})
        doc = yaml.safe_load(config.read_text())
        self.assertEqual((config.parent / doc['source_ifc']).resolve(), source)
        self.assertEqual((directory/project['authority']['physical_geometry']).resolve(),source)

    def test_imported_source_hash_preserved(self):
        fixture = json.loads((ROOT / 'tests/fixtures/a01_input_signature.json').read_text())
        directory,project,_,_,_=load_project(PROJECT)
        self.assertEqual(file_hash(received_scheme(directory,project)), fixture['source_ifc_sha256'])

    def test_preliminary_input_validation(self):
        result = validate(PROJECT)
        self.assertEqual(result['physical_counts']['IFCCOLUMN'], 36)
        self.assertEqual(result['physical_counts']['IFCBEAM'], 51)
        self.assertFalse(result['solver_executed'])
        self.assertFalse(result['engineering_approval'])

    def test_step_reader_resolves_references(self):
        model = Model(PROJECT / 'structural/inputs/structural.ifc')
        model.validate_refs()
        self.assertEqual(len(model.by_type('IFCPROJECT')), 1)

    def test_step_value_roundtrip(self):
        value = ('quoted \' text', Ref(12), Typed('IFCREAL', (2.5,)))
        self.assertEqual(parse(encode(value)), value)

    def test_code_parses(self):
        for file in (ROOT / 'src').rglob('*.py'):
            with self.subTest(file=file.name):
                ast.parse(file.read_text(encoding='utf-8'))

    def test_full_case_scope_tracked(self):
        checklist = yaml.safe_load((PROJECT / 'structural/design/checklist.yaml').read_text())
        stages = {s['id']:s for s in checklist['stages']}
        for name in ('architectural_input', 'analysis', 'rc_design', 'foundation', 'deliverables',
                     'iteration', 'cost_control', 'constructability', 'industry_comparison'):
            self.assertIn(name, stages)
        self.assertIn(stages['analysis']['status'], ('NOT_RUN', 'DIAGNOSTIC_VERIFIED'))
        if stages['analysis']['status'] == 'DIAGNOSTIC_VERIFIED':
            self.assertTrue(stages['analysis']['evidence'])
        for stage in stages.values():
            for relative in stage['evidence']:
                self.assertTrue((PROJECT/'structural/design'/relative).is_file())
        with (PROJECT / 'comparison/workflow.csv').open() as stream:
            matrix = {row['stage_id']: row for row in csv.DictReader(stream)}
        self.assertEqual(set(stages), set(matrix))
        for name, row in matrix.items():
            self.assertEqual(row['our_stage_status'], stages[name]['status'], name)
            for relative in row['evidence_paths'].split(';'):
                self.assertTrue((PROJECT/'comparison'/relative).is_file(), relative)

    def test_license_notice_preserved(self):
        notice = (ROOT / 'LICENSES/imported-code-MIT.txt').read_text()
        self.assertIn('MIT License', notice)
        self.assertIn('not to dependency libraries', notice)
        self.assertTrue((ROOT / 'THIRD_PARTY_NOTICES.md').is_file())

    def test_adopted_input_and_reviewed_output_identities(self):
        # Path edits must preserve actual source binding, not merely valid links.
        project = yaml.safe_load((PROJECT/'project.yaml').read_text())
        receipt = json.loads((PROJECT/project['release']['diagnostic_adoption_record']).read_text())
        for name in ('project/project.yaml', 'project/structural/inputs/structural.ifc',
                     'project/structural/inputs/analysis.yaml'):
            self.assertEqual(file_hash(ROOT/name), receipt['after_sha256'][name], name)
        drawings = json.loads((ROOT/receipt['reviewed_outputs_manifest']).read_text())
        self.assertEqual(drawings['source_sha256'], file_hash(PROJECT/'structural/inputs/structural.ifc'))
        for name, digest in drawings['reviewed_output_sha256'].items():
            self.assertEqual(file_hash(ROOT/name), digest, name)

    def test_run_records_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            first, a = make_run(p, 'a01', 'test')
            second, b = make_run(p, 'a01', 'test')
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, p / RUNS_RELATIVE)
            self.assertEqual(a['layout_version'], 2)
            (first / 'log.txt').write_text('example\n')
            finish_run(first, a, 'FAILED', exit_code=2)
            final = json.loads((first / 'manifest.json').read_text())
            self.assertEqual(final['status'], 'FAILED')
            self.assertFalse(final['solver_executed'])
            self.assertFalse(final['engineering_approval'])
            self.assertIn('log.txt', final['output_sha256'])

    def test_run_output_is_excluded_from_input_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'project/structural/inputs/example.yaml'
            source.parent.mkdir(parents=True)
            source.write_text('authoritative input')
            before = inventory(root)
            run, manifest = make_run(root, 'a01', 'test')
            (run / 'raw-result.csv').write_text('generated result')
            finish_run(run, manifest, 'COMPLETED_TEST_ONLY')
            self.assertEqual(inventory(root), before)
            self.assertIn(source.relative_to(root).as_posix(), before)
            source.write_text('changed authoritative input')
            self.assertNotEqual(inventory(root), before)

    def test_relocated_build_requires_unchanged_input_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'project/structural/inputs/analysis.yaml'
            source.parent.mkdir(parents=True)
            source.write_text('original settings')
            old_key = 'projects/a01/inputs/analysis.yaml'
            parent = {'input_and_source_sha256': {old_key: file_hash(source)}}
            verify_build_inputs(root, parent, (source,))
            source.write_text('changed settings')
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                verify_build_inputs(root, parent, (source,))

    def test_current_build_cannot_fall_back_to_legacy_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'project/structural/inputs/analysis.yaml'
            source.parent.mkdir(parents=True)
            source.write_text('settings')
            hashes = {'projects/a01/inputs/analysis.yaml': file_hash(source)}
            parent = {'layout_version': 2, 'input_and_source_sha256': hashes}
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                verify_build_inputs(root, parent, (source,))
            hashes[source.relative_to(root).as_posix()] = file_hash(source)
            verify_build_inputs(root, parent, (source,))
            parent['layout_version'] = 1
            hashes[source.relative_to(root).as_posix()] = 'conflicting hash'
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                verify_build_inputs(root, parent, (source,))

    def test_cli_defaults_to_single_project(self):
        with patch('structural_ai.cli.validate', return_value={}) as check, patch('builtins.print'):
            self.assertEqual(main(['validate']), 0)
        check.assert_called_once_with(Path('project'))

    def test_solver_rejects_changed_architectural_scheme(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project=root/'project';project.mkdir()
            source=project/'structural.ifc';source.write_text('source placeholder')
            cfg=project/'analysis.yaml';cfg.write_text('analysis placeholder')
            scheme=project/'scheme.yaml';scheme.write_text('revision: H02\nfinish: 1.5\n')
            build=root/RUNS_RELATIVE/'test-build';build.mkdir(parents=True)
            model=build/'analytical_model.json';model.write_text('{}')
            parent={'layout_version':2,'task':'build','status':'COMPLETED_GEOMETRY_AND_ANALYSIS_INPUTS_ONLY',
                    'output_sha256':{'analytical_model.json':file_hash(model)},
                    'input_and_source_sha256':{p.relative_to(root).as_posix():file_hash(p) for p in (source,cfg,scheme)}}
            (build/'manifest.json').write_text(json.dumps(parent))
            scheme.write_text('revision: H02\nfinish: 2.0\n')
            doc={'id':'a01','inputs':{'architectural_scheme':'scheme.yaml'}}
            with patch('structural_ai.cli.load_project',return_value=(project,doc,source,cfg,root)):
                with self.assertRaisesRegex(ValueError,'Inputs changed'):
                    analyze_project(project,model,'all',12)

    def test_scope_and_publication_separated(self):
        p = yaml.safe_load((PROJECT / 'project.yaml').read_text())
        self.assertFalse(p['release']['design_complete'])
        self.assertFalse(p['release']['public_publication_requested'])
        agents = (ROOT / 'AGENTS.md').read_text()
        self.assertIn('Do not reduce the scope', agents)
        self.assertIn('do not publish', agents.lower())

    def test_immutable_received_source_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'received.ifc';source.write_text('received source')
            project={'inputs':{'structural_ifc':'active.ifc','received_structural_scheme':'received.ifc'},
                     'compatibility':{'source_ifc_sha256':'active-hash','received_source_sha256':file_hash(source)}}
            self.assertEqual(received_scheme(root,project),source)
            source.write_text('unreviewed edit')
            with self.assertRaisesRegex(ValueError,'Immutable received scheme changed'):
                received_scheme(root,project)

    def test_solver_rejects_changed_equipment_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project=root/'project';project.mkdir()
            source=project/'structural.ifc';source.write_text('source placeholder')
            cfg=project/'analysis.yaml';cfg.write_text('analysis placeholder')
            scheme=project/'scheme.yaml';scheme.write_text('revision: H02\n')
            equipment=project/'equipment.yaml';equipment.write_text('synthetic_weight_kN: 20\n')
            build=root/RUNS_RELATIVE/'test-build';build.mkdir(parents=True)
            model=build/'analytical_model.json';model.write_text('{}')
            parent={'layout_version':2,'task':'build','status':'COMPLETED_GEOMETRY_AND_ANALYSIS_INPUTS_ONLY',
                    'output_sha256':{'analytical_model.json':file_hash(model)},
                    'input_and_source_sha256':{p.relative_to(root).as_posix():file_hash(p) for p in (source,cfg,scheme,equipment)}}
            (build/'manifest.json').write_text(json.dumps(parent))
            equipment.write_text('synthetic_weight_kN: 40\n')
            doc={'id':'a01','inputs':{'architectural_scheme':'scheme.yaml','equipment_basis':'equipment.yaml'}}
            with patch('structural_ai.cli.load_project',return_value=(project,doc,source,cfg,root)),patch('structural_ai.cli.subprocess.run') as solver:
                with self.assertRaisesRegex(ValueError,'Inputs changed'):
                    analyze_project(project,model,'all',12)
                solver.assert_not_called()


if __name__ == '__main__':
    unittest.main()
