import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "algorithm" / "discor"))
sys.path.insert(0, str(REPO_ROOT / "assetto_corsa_gym"))

from discor.agent import Agent


def make_agent(tmp_path):
    agent = Agent.__new__(Agent)
    agent._env = Mock()
    agent._test_env = Mock()
    agent._writer = Mock()
    agent.wandb_logger = None
    agent.external_checkpoint_enabled = True
    agent.external_checkpoint_poll_interval_steps = 25
    agent.external_checkpoint_control_dir = tmp_path / "control"
    agent._external_checkpoint_request_path = (
        agent.external_checkpoint_control_dir / "save_checkpoint.request.json")
    agent._external_checkpoint_processing_path = (
        agent.external_checkpoint_control_dir / "save_checkpoint.processing.json")
    agent._last_external_checkpoint_poll_step = 0
    agent._external_stop_requested = False
    agent._steps = 125
    agent.checkpoint_step_offset = 1_000
    agent._model_dir = str(tmp_path / "model")
    agent._last_replay_checkpoint_path = "previous.ckpt"
    agent._last_replay_total_appends = 100
    return agent


class ExternalCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_claim_external_checkpoint_request_is_atomic(self):
        agent = make_agent(self.tmp_path)
        request = {
            "request_id": "request-123",
            "requested_at": "2026-08-11T20:00:00",
            "stop_after_save": True,
        }
        Agent._write_json_atomic(agent._external_checkpoint_request_path, request)

        claimed = agent._claim_external_checkpoint_request()

        self.assertEqual(claimed, request)
        self.assertFalse(agent._external_checkpoint_request_path.exists())
        self.assertTrue(agent._external_checkpoint_processing_path.exists())
        self.assertIsNone(agent._claim_external_checkpoint_request())

    def test_external_checkpoint_is_published_only_after_complete_save(self):
        agent = make_agent(self.tmp_path)
        agent._external_checkpoint_processing_path.parent.mkdir(parents=True)
        agent._external_checkpoint_processing_path.write_text("{}", encoding="utf-8")

        def fake_save(directory, save_buffer=False):
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            for name in (
                    "policy_net.pth", "online_q_net.pth", "target_q_net.pth"):
                (directory / name).write_bytes(b"model")

        def fake_save_training_checkpoint(directory):
            directory = Path(directory)
            (directory / "replay_delta.npz").write_bytes(b"replay")
            checkpoint_path = directory / "training_state.ckpt"
            checkpoint_path.write_bytes(b"state")
            agent._last_replay_checkpoint_path = str(checkpoint_path)
            agent._last_replay_total_appends = 125
            return checkpoint_path

        agent.save = fake_save
        agent.save_training_checkpoint = fake_save_training_checkpoint
        request = {
            "request_id": "request-456",
            "requested_at": "2026-08-11T20:00:00",
            "stop_after_save": True,
        }

        checkpoint_path = agent._save_external_checkpoint(request)

        expected_dir = (
            self.tmp_path / "model" / "checkpoints" /
            "step_00001125_external_request-456")
        self.assertEqual(checkpoint_path, expected_dir / "training_state.ckpt")
        self.assertTrue(checkpoint_path.exists())
        self.assertTrue((expected_dir / "replay_delta.npz").exists())
        self.assertFalse(any(
            path.name.endswith(".tmp")
            for path in (self.tmp_path / "model" / "checkpoints").iterdir()
        ))
        status_path = (
            self.tmp_path / "control" /
            "checkpoint.status.request-456.json")
        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "success")
        self.assertEqual(status["total_step"], 1125)
        self.assertEqual(status["checkpoint_path"], str(checkpoint_path.resolve()))
        self.assertEqual(
            agent._last_replay_checkpoint_path,
            str(checkpoint_path.resolve()),
        )
        self.assertTrue(agent._external_stop_requested)
        self.assertFalse(agent._external_checkpoint_processing_path.exists())


if __name__ == "__main__":
    unittest.main()
