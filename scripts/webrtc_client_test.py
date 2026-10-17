"""Standalone aiortc test client for the webrtc_app.py experiment.

Sends a synthetic video track to the running fastrtc WebRTC gradio
component (no browser involved) using gradio's component_server RPC, and
measures time-to-first-frame and steady-state received fps.

Usage: python webrtc_client_test.py [base_url] [component_id] [seconds]
"""
import asyncio
import sys
import time
import uuid

import httpx
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

APP_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7863"
COMPONENT_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 6
DURATION_S = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
COMPONENT_SERVER = f"{APP_URL}/gradio_api/component_server"


class SyntheticTrack(VideoStreamTrack):
    def __init__(self, w=640, h=480):
        super().__init__()
        self.w, self.h = w, h
        self._n = 0

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        self._n += 1
        arr = np.full((self.h, self.w, 3), (self._n * 4) % 255, dtype=np.uint8)
        frame = VideoFrame.from_ndarray(arr, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


async def main():
    pc = RTCPeerConnection()
    webrtc_id = str(uuid.uuid4())
    pc.addTrack(SyntheticTrack())
    # FastRTC's VideoCallback.recv() blocks on wait_for_channel() until the
    # client opens a data channel (its JS frontend always does this); without
    # it the server never processes a single video frame.
    pc.createDataChannel("text")

    @pc.on("connectionstatechange")
    async def on_cs():
        print("connectionState ->", pc.connectionState)

    @pc.on("iceconnectionstatechange")
    async def on_ics():
        print("iceConnectionState ->", pc.iceConnectionState)

    @pc.on("icegatheringstatechange")
    async def on_igs():
        print("iceGatheringState ->", pc.iceGatheringState)

    recv_times: list[float] = []
    first_recv = {}

    @pc.on("track")
    def on_track(remote_track):
        print("got remote track:", remote_track.kind)
        async def reader():
            while True:
                try:
                    await remote_track.recv()
                except Exception:
                    break
                now = time.monotonic()
                first_recv.setdefault("t", now)
                recv_times.append(now)

        asyncio.ensure_future(reader())

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    async with httpx.AsyncClient(timeout=20.0) as client:
        t_sent = time.monotonic()
        resp = await client.post(
            COMPONENT_SERVER,
            json={
                "session_hash": str(uuid.uuid4()),
                "component_id": COMPONENT_ID,
                "fn_name": "offer",
                "data": {
                    "sdp": pc.localDescription.sdp,
                    "type": pc.localDescription.type,
                    "webrtc_id": webrtc_id,
                },
            },
        )
        resp.raise_for_status()
        answer = resp.json()
        print("signaling response status:", answer.get("status", answer.get("type")))
        if "sdp" not in answer:
            print("FAILED: no sdp in answer:", answer)
            await pc.close()
            return
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

    await asyncio.sleep(DURATION_S)
    await pc.close()

    if recv_times:
        time_to_first_ms = (first_recv["t"] - t_sent) * 1000
        span = recv_times[-1] - recv_times[0]
        fps = (len(recv_times) - 1) / span if span > 0 else 0.0
        print(f"frames received: {len(recv_times)}")
        print(f"time to first frame: {time_to_first_ms:.0f} ms")
        print(f"steady-state fps: {fps:.1f}")
    else:
        print("FAILED: no frames received back from the server.")


asyncio.run(main())
