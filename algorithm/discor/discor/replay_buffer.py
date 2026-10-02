from collections import deque
from pathlib import Path
import numpy as np
import torch

import logging
logger = logging.getLogger(__name__)


class NStepBuffer:
    def __init__(self, gamma=0.99, nstep=3):
        assert isinstance(gamma, float) and 0 < gamma < 1.0
        assert isinstance(nstep, int) and nstep > 0

        self._discounts = [gamma ** i for i in range(nstep)]
        self._nstep = nstep
        self.reset()

    def append(self, state, action, reward):
        self._states.append(state)
        self._actions.append(action)
        self._rewards.append(reward)

    def get(self):
        assert len(self._rewards) > 0

        state = self._states.popleft()
        action = self._actions.popleft()
        reward = self._nstep_reward()
        return state, action, reward

    def _nstep_reward(self):
        reward = np.sum([
            r * d for r, d in zip(self._rewards, self._discounts)])
        self._rewards.popleft()
        return reward

    def reset(self):
        self._states = deque(maxlen=self._nstep)
        self._actions = deque(maxlen=self._nstep)
        self._rewards = deque(maxlen=self._nstep)

    def is_empty(self):
        return len(self._rewards) == 0

    def is_full(self):
        return len(self._rewards) == self._nstep

    def __len__(self):
        return len(self._rewards)


class ReplayBuffer:
    def __init__(self, memory_size, state_shape, action_shape, gamma=0.99, nstep=1):
        assert isinstance(memory_size, int) and memory_size > 0
        assert isinstance(state_shape, tuple)
        assert isinstance(action_shape, tuple)
        assert isinstance(gamma, float) and 0 < gamma < 1.0
        assert isinstance(nstep, int) and nstep > 0

        self._memory_size = memory_size
        self._state_shape = state_shape
        self._action_shape = action_shape
        self._gamma = gamma
        self._nstep = nstep
        self._reset()

    def _reset(self):
        self._n = 0
        self._p = 0
        self._total_appends = 0

        self._states = np.empty(
            (self._memory_size, ) + self._state_shape, dtype=np.float32)
        self._next_states = np.empty(
            (self._memory_size, ) + self._state_shape, dtype=np.float32)
        self._actions = np.empty(
            (self._memory_size, ) + self._action_shape, dtype=np.float32)

        self._rewards = np.empty((self._memory_size, 1), dtype=np.float32)
        self._dones = np.empty((self._memory_size, 1), dtype=np.float32)

        if self._nstep != 1:
            self._nstep_buffer = NStepBuffer(self._gamma, self._nstep)
        logger.info(f"Replay buffer initialized for {self._memory_size} samples")

    def append(self, state, action, reward, next_state, terminated, episode_done=None):
        """
        done (masked_done): False if the agent reach time horizons. Else = done
        """
        if self._nstep != 1:
            self._nstep_buffer.append(state, action, reward)

            if self._nstep_buffer.is_full():
                state, action, reward = self._nstep_buffer.get()
                self._append(state, action, reward, next_state, terminated)

            if terminated or episode_done:
                while not self._nstep_buffer.is_empty():
                    state, action, reward = self._nstep_buffer.get()
                    self._append(state, action, reward, next_state, terminated)

        else:
            self._append(state, action, reward, next_state, terminated)

    def _append(self, state, action, reward, next_state, done):
        self._states[self._p, ...] = state
        self._actions[self._p, ...] = action
        self._rewards[self._p, ...] = reward
        self._next_states[self._p, ...] = next_state
        self._dones[self._p, ...] = done

        self._n = min(self._n + 1, self._memory_size)
        self._p = (self._p + 1) % self._memory_size
        self._total_appends += 1

    def save_delta(self, path, since_total_appends=0):
        """Persist only replay slots changed since the previous checkpoint."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Buffers pickled by older versions do not have this counter.  Their
        # current contents are still a valid full starting snapshot.
        total_appends = getattr(self, "_total_appends", self._n)
        changed = total_appends - int(since_total_appends)
        full_snapshot = changed < 0 or changed >= self._memory_size

        if full_snapshot:
            indices = np.arange(self._n if self._n < self._memory_size else self._memory_size)
        elif changed == 0:
            indices = np.empty(0, dtype=np.int64)
        else:
            changed = min(changed, self._n)
            start = (self._p - changed) % self._memory_size
            if start < self._p:
                indices = np.arange(start, self._p)
            else:
                indices = np.concatenate((
                    np.arange(start, self._memory_size),
                    np.arange(0, self._p),
                ))

        np.savez(
            path,
            indices=indices,
            states=self._states[indices],
            next_states=self._next_states[indices],
            actions=self._actions[indices],
            rewards=self._rewards[indices],
            dones=self._dones[indices],
            n=np.asarray(self._n, dtype=np.int64),
            p=np.asarray(self._p, dtype=np.int64),
            total_appends=np.asarray(total_appends, dtype=np.int64),
            memory_size=np.asarray(self._memory_size, dtype=np.int64),
        )
        return {
            "changed_slots": int(len(indices)),
            "total_appends": int(total_appends),
            "full_snapshot": bool(full_snapshot),
        }

    def load_delta(self, path):
        """Apply one replay delta produced by :meth:`save_delta`."""
        with np.load(path, allow_pickle=False) as delta:
            memory_size = int(delta["memory_size"])
            if memory_size != self._memory_size:
                raise ValueError(
                    f"Replay memory size mismatch: checkpoint={memory_size}, "
                    f"configured={self._memory_size}")

            indices = delta["indices"].astype(np.int64, copy=False)
            self._states[indices] = delta["states"]
            self._next_states[indices] = delta["next_states"]
            self._actions[indices] = delta["actions"]
            self._rewards[indices] = delta["rewards"]
            self._dones[indices] = delta["dones"]
            self._n = int(delta["n"])
            self._p = int(delta["p"])
            self._total_appends = int(delta["total_appends"])

        if self._nstep != 1:
            self._nstep_buffer.reset()

    def sample(self, batch_size, device=torch.device('cpu')):
        assert isinstance(batch_size, int) and batch_size > 0

        idxes = self._sample_idxes(batch_size)
        return self._sample_batch(idxes, batch_size, device)

    def _sample_idxes(self, batch_size):
        return np.random.randint(low=0, high=self._n, size=batch_size)

    def _sample_batch(self, idxes, batch_size, device):
        states = torch.tensor(
            self._states[idxes], dtype=torch.float, device=device)
        actions = torch.tensor(
            self._actions[idxes], dtype=torch.float, device=device)
        rewards = torch.tensor(
            self._rewards[idxes], dtype=torch.float, device=device)
        dones = torch.tensor(
            self._dones[idxes], dtype=torch.float, device=device)
        next_states = torch.tensor(
            self._next_states[idxes], dtype=torch.float, device=device)

        return states, actions, rewards, next_states, dones

    def __len__(self):
        return self._n


class EnsembleBuffer(ReplayBuffer):
    """
    Ensemble of an offline dataloader and an online replay buffer.
    """
    def __init__(self, memory_size, state_shape, action_shape, offline_buffer_size, gamma=0.99, nstep=1):
        # Initialize the offline buffer with the specified offline_buffer_size
        self._offline = ReplayBuffer(offline_buffer_size, state_shape, action_shape, gamma, nstep)

        # Initialize the online buffer using the parent class constructor
        super().__init__(memory_size, state_shape, action_shape, gamma, nstep)
        self._online = False

    def online(self, enable):
        """Enable or disable sampling from the online buffer."""
        self._online = enable
        if enable:
            logger.info("Switching to Online buffer.")

    def append(self, state, action, reward, next_state, terminated, episode_done=None):
        if self._online:
            super().append(state, action, reward, next_state, terminated, episode_done)
        else:
            self._offline.append(state, action, reward, next_state, terminated, episode_done)

    def __len__(self):
        offline_len = len(self._offline)
        online_len = super().__len__()
        logger.info(f"Offline buffer size: {offline_len}, Online buffer size: {online_len}.")
        return offline_len + online_len

    def sample(self, batch_size, device=torch.device('cpu')):
        """Sample a batch of data from the two buffers."""
        obs0, action0, reward0, next_states0, dones0 = self._offline.sample(batch_size // 2, device)
        obs1, action1, reward1, next_states1, dones1 = (super() if self._online else self._offline).sample(batch_size // 2, device)

        # Concatenate samples from both buffers
        states = torch.cat([obs0, obs1], dim=0)
        actions = torch.cat([action0, action1], dim=0)
        rewards = torch.cat([reward0, reward1], dim=0)
        next_states = torch.cat([next_states0, next_states1], dim=0)
        dones = torch.cat([dones0, dones1], dim=0)

        return states, actions, rewards, next_states, dones
