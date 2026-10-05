import sys
import tempfile
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'algorithm/discor'))
from discor.algorithm.sac import SAC


def test_anchor_is_frozen_and_detects_student_drift():
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / 'teacher.pth')
        baseline = SAC(4, 3, torch.device('cpu'), policy_hidden_units=[8], q_hidden_units=[8])
        torch.save(baseline._policy_net.state_dict(), path)
        anchored = SAC(4, 3, torch.device('cpu'), policy_hidden_units=[8], q_hidden_units=[8],
                       policy_anchor_path=path, policy_anchor_coef=5.)
        anchored._policy_net.load_state_dict(baseline._policy_net.state_dict())
        states = torch.ones(6, 4)
        assert anchored.calc_anchor_loss(states).item() == 0.
        before = {k: v.clone() for k, v in anchored._policy_anchor.state_dict().items()}
        with torch.no_grad():
            list(anchored._policy_net.parameters())[-1].add_(.1)
        loss = anchored.calc_anchor_loss(states)
        assert loss.item() > 0
        loss.backward()
        assert all(p.grad is None for p in anchored._policy_anchor.parameters())
        assert any(p.grad is not None for p in anchored._policy_net.parameters())
        assert all(torch.equal(before[k], v) for k, v in anchored._policy_anchor.state_dict().items())


def test_disabled_anchor_does_not_change_rng_or_loss():
    a = SAC(4, 3, torch.device('cpu'), policy_hidden_units=[8], q_hidden_units=[8], seed=4)
    b = SAC(4, 3, torch.device('cpu'), policy_hidden_units=[8], q_hidden_units=[8], seed=4,
            policy_anchor_coef=0.)
    states = torch.ones(6, 4)
    torch.manual_seed(12)
    x, _ = a.calc_policy_loss(states)
    torch.manual_seed(12)
    y, _ = b.calc_policy_loss(states)
    assert torch.equal(x, y)


def test_critic_warmup_freezes_actor_then_releases():
    agent = SAC(4, 3, torch.device('cpu'), policy_hidden_units=[8], q_hidden_units=[8],
                policy_freeze_until_learning_step=1)
    class Writer:
        def add_scalar(self, *args):
            pass
    batch = (torch.ones(6, 4), torch.zeros(6, 3), torch.ones(6, 1),
             torch.ones(6, 4), torch.zeros(6, 1))
    before = {k: v.clone() for k, v in agent._policy_net.state_dict().items()}
    q_before = {k: v.clone() for k, v in agent._online_q_net.state_dict().items()}
    agent.update_online_networks(batch, Writer())
    assert all(torch.equal(before[k], v) for k, v in agent._policy_net.state_dict().items())
    assert any(not torch.equal(q_before[k], v) for k, v in agent._online_q_net.state_dict().items())
    agent.update_online_networks(batch, Writer())
    assert any(not torch.equal(before[k], v) for k, v in agent._policy_net.state_dict().items())
