"""Validate the deployed catalog against the fixed-slot inference contract.

These checks load metadata only: no database, HTTP server or ONNX session.
"""

import unittest

import numpy as np

from app_monitor.huiyan_runtime import engine


class HuiyanCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine.ensure_metadata()
        if not engine.SESSION["metadata_ready"]:
            raise AssertionError(engine.SESSION["metadata_error"])

    def test_every_category_prompt_can_be_inferred(self):
        for name, config in engine.SESSION["cats"].items():
            with self.subTest(category=name):
                targets = engine.resolve_category(name)
                self.assertEqual(len(targets), len(config["words"]))
                self.assertGreater(len(targets), 0)
                self.assertLessEqual(len(targets), engine.SLOTS)
                self.assertEqual([t[0] for t in targets], [w["en"] for w in config["words"]])
                self.assertTrue(all(t[1] == name for t in targets))
                features = engine.build_txt_feats(targets)
                self.assertEqual(features.shape, (1, engine.SLOTS, 512))
                self.assertTrue(np.isfinite(features).all())

    def test_every_subset_has_species_and_auxiliary_embeddings(self):
        for name, config in engine.SESSION["cats"].items():
            for subset in config.get("subs", []):
                with self.subTest(category=name, subset=subset["name"]):
                    targets = engine.resolve_targets(subset["classes"])
                    self.assertEqual(len(targets), len(subset["classes"]))
                    self.assertGreater(len(targets), 0)
                    aux = engine.resolve_phrase(subset["phrase"]) if subset.get("phrase") else []
                    if subset.get("phrase"):
                        self.assertEqual(len(aux), 1)
                    self.assertLessEqual(len(targets) + len(aux), engine.SLOTS)
                    self.assertTrue(np.isfinite(engine.build_txt_feats_with_aux(targets, aux)).all())

    def test_category_falls_back_to_matching_species_without_relabeling(self):
        missing = [(name,w["en"]) for name,cfg in engine.SESSION["cats"].items()
                   for w in cfg["words"] if w["en"] not in engine.SESSION["cat_emb"]]
        self.assertTrue(missing, "Updated catalog should exercise the shared species vectors")
        for name, prompt in missing:
            with self.subTest(category=name, prompt=prompt):
                category_target = next(t for t in engine.resolve_category(name) if t[0] == prompt)
                species_target = engine.resolve_targets([prompt])[0]
                np.testing.assert_array_equal(category_target[2], species_target[2])
                self.assertEqual(category_target[1], name)
