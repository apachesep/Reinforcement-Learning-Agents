import numpy as np
from ple import PLE
import random
from ple.games.flappybird import FlappyBird
import tensorflow as tf
from collections import deque
import os
import pickle

class Agent:

    LEARNING_RATE = 0.003
    BATCH_SIZE = 32
    INPUT_SIZE = 8
    LAYER_SIZE = 500
    OUTPUT_SIZE = 2
    EPSILON = 1
    DECAY_RATE = 0.005
    MIN_EPSILON = 0.1
    GAMMA = 0.99
    MEMORIES = deque()
    INITIAL_FEATURES = np.zeros((4, INPUT_SIZE))
    MEMORY_SIZE = 300
    # based on documentation, features got 8 dimensions
    # output is 2 dimensions, 0 = do nothing, 1 = jump

    def __init__(self, screen=False, forcefps=True):
        self.game = FlappyBird(pipe_gap=125)
        self.env = PLE(self.game, fps=30, display_screen=screen, force_fps=forcefps)
        self.env.init()
        self.env.getGameState = self.game.getGameState
        self.X = tf.placeholder(tf.float32, (None, None, input_size))
        self.Y = tf.placeholder(tf.float32, (None, output_size))
        cell = tf.nn.rnn_cell.LSTMCell(512, state_is_tuple = False)
        self.hidden_layer = tf.placeholder(tf.float32, (None, 2 * 512))
        self.rnn,self.last_state = tf.nn.dynamic_rnn(inputs=self.X,cell=cell,
                                                    dtype=tf.float32,
                                                    initial_state=self.hidden_layer)
        w = tf.Variable(tf.random_normal([512, output_size]))
        self.logits = tf.matmul(self.rnn[:,-1], w)
        self.cost = tf.reduce_sum(tf.square(self.Y - self.logits))
        self.optimizer = tf.train.AdamOptimizer(learning_rate = self.LEARNING_RATE).minimize(self.cost)
        self.sess = tf.InteractiveSession()
        self.sess.run(tf.global_variables_initializer())
        self.saver = tf.train.Saver(tf.global_variables())
        self.rewards = []

    def _memorize(self, state, action, reward, new_state, dead, rnn_state):
        self.MEMORIES.append((state, action, reward, new_state, dead, rnn_state))
        if len(self.MEMORIES) > self.MEMORY_SIZE:
            self.MEMORIES.popleft()

    def _construct_memories(self, replay):
        states = np.array([a[0] for a in replay])
        new_states = np.array([a[3] for a in replay])
        init_values = np.array([a[-1] for a in replay])
        Q = sess.run(self.logits, feed_dict={self.X:states, self.hidden_layer:init_values})
        Q_new = sess.run(self.logits, feed_dict={self.X:new_states, self.hidden_layer:init_values})
        replay_size = len(replay)
        X = np.empty((replay_size, self.INPUT_SIZE))
        Y = np.empty((replay_size, self.OUTPUT_SIZE))
        for i in range(replay_size):
            state_r, action_r, reward_r, new_state_r, dead_r = replay[i]
            target = Q[i]
            target[action_r] = reward_r
            if not dead_r:
                target[action_r] += self.GAMMA * np.amax(Q_new[i])
            X[i] = state_r
            Y[i] = target
        return X, Y

    def save(self, checkpoint_name):
        self.saver.save(self.sess, os.getcwd() + "/%s.ckpt" %(checkpoint_name))
        with open('%s-acc.p'%(checkpoint_name), 'wb') as fopen:
            pickle.dump(self.rewards, fopen)

    def load(self, checkpoint_name):
        self.saver.restore(self.sess, os.getcwd() + "/%s.ckpt" %(checkpoint_name))
        with open('%s-acc.p'%(checkpoint_name), 'rb') as fopen:
            self.rewards = pickle.load(fopen)

    def get_predicted_action(self, sequence):
        prediction = self.predict(np.array(sequence))[0]
        return np.argmax(prediction)

    def get_state(self):
        state = self.env.getGameState()
        return np.array(list(state.values()))

    def get_reward(self, iterations, checkpoint):
        for i in range(iterations):
            total_reward = 0
            self.env.reset_game()
            dead = False
            init_value = np.zeros((1, 2 * 512))
            state = self.get_state()
            for i in range(self.INITIAL_FEATURES.shape[0]):
                self.INITIAL_FEATURES[i,:] = state
            while not dead:
                if (self.T_COPY + 1) % self.COPY == 0:
                    self._assign()
                if np.random.rand() < self.EPSILON:
                    action = np.random.randint(self.OUTPUT_SIZE)
                else:
                    action, last_state = sess.run(self.model.logits,
                                                  self.model.last_state,
                                                  feed_dict={self.model.X:[self.INITIAL_FEATURES],
                                                             self.model.hidden_layer:init_values})
                    action, init_value = np.argmax(action[0]), last_state[0]
                real_action = 119 if action == 1 else None
                reward = self.env.act(real_action)
                total_reward += reward
                new_state = np.append(self.get_state(), self.INITIAL_FEATURES[:3, :], axis = 0)
                dead = self.env.game_over()
                self._memorize(state, action, reward, new_state, dead, init_value)
                batch_size = min(len(self.MEMORIES), self.BATCH_SIZE)
                replay = random.sample(self.MEMORIES, batch_size)
                cost = self._construct_memories(replay)
                self.EPSILON = self.MIN_EPSILON + (1.0 - self.MIN_EPSILON) * np.exp(-self.DECAY_RATE * i)
                self.T_COPY += 1
            self.rewards.append(total_reward)
            self.EPSILON = self.MIN_EPSILON + (1.0 - self.MIN_EPSILON) * np.exp(-self.DECAY_RATE * i)
            if (i+1) % checkpoint == 0:
                print('epoch:', i + 1, 'total rewards:', total_reward)
                print('epoch:', i + 1, 'cost:', cost)

    def fit(self, iterations, checkpoint):
        self.get_reward(iterations, checkpoint)
