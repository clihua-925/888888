# -*- coding: utf-8 -*-
"""StateBroadcaster v43: 后台→UI 单向广播层，根治后台与UI不同步问题。"""
import json, queue, threading, time

class StateBroadcaster:
    """所有后台线程通过此处推事件，Web UI 通过 SSE 或轮询消费。"""
    def __init__(self):
        self._queues = []
        self._lock = threading.Lock()
        self._history = []
        self._max_history = 500

    def subscribe(self):
        q = queue.Queue(maxsize=200)
        with self._lock:
            self._queues.append(q)
            for ev in self._history[-100:]:
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    break
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._queues:
                self._queues.remove(q)

    def emit(self, event_type, payload):
        ev = {"type": event_type, "payload": payload, "ts": time.time()}
        self._history.append(ev)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        dead = []
        with self._lock:
            for q in self._queues:
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                if q in self._queues:
                    self._queues.remove(q)

    def get_history(self, last_ts=0, limit=50):
        return [e for e in self._history if e["ts"] > last_ts][-limit:]

# 全局单例
_broadcaster = StateBroadcaster()
def get_broadcaster():
    return _broadcaster
