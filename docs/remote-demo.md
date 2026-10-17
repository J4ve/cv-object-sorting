# How the midterm demo was presented live over Google Meet

This documents how we presented the object-sorting demo for the midterm:
one presenter runs the Gradio app locally and screen-shares it in Google
Meet, while groupmates join from their own homes and use their **phones**
as the camera source. Each groupmate points their phone at a different
everyday object, which gave the demo varied real-world viewpoints,
backgrounds, and lighting without anyone needing to bring physical props
to one location. The presenter just switches the active camera from a
dropdown in the Gradio UI to flip between phones live, on screen, for
everyone on the call.

This is a description of how that one session was run, not a plan for
permanent infrastructure — there's no dedicated hardware or server for
this project; it borrowed a VPS someone already had running for something
else, for the duration of the demo.

## Why phones need HTTPS

Browsers only grant camera access (`getUserMedia`) to a page served over
HTTPS (or `localhost`). A phone on a groupmate's home network opening the
presenter's laptop over plain HTTP would get the camera permission
silently denied. So the Gradio app's local URL had to be reachable over
**HTTPS** from the open internet, not just on the presenter's own LAN.

## How it worked: a reverse SSH tunnel through a cloud VPS

The presenter's Gradio app only listens on `127.0.0.1:7860` on their own
laptop — it was never exposed directly to the internet. Instead:

<p align="center"><img src="images/remote-demo-flow.svg" width="650" alt="Groupmate's phone connects over HTTPS to Caddy on the VPS, which is linked by a reverse SSH tunnel to the Gradio app on the presenter's laptop"><br><sub>Figure 1. A phone's HTTPS request reaches Caddy on the VPS, which hands off through the reverse SSH tunnel to the Gradio app on the presenter's own laptop.</sub></p>

1. **A small cloud VPS** (`<vps-ip>`) already ran [Caddy](https://caddyserver.com/)
   as its web server/reverse proxy for other things.
2. We gave the VPS a hostname via **sslip.io**, a free DNS service that
   maps `<ip-with-dashes>.sslip.io` to that IP automatically — no DNS
   registrar or manual records needed. Caddy requests a Let's Encrypt
   certificate for that hostname **on demand**, the first time it's
   visited, which is what makes it serve valid HTTPS with zero manual
   cert setup.
3. Caddy was given one extra site block that reverse-proxies that
   hostname to a local port on the VPS, e.g.:
   ```caddy
   demo.<ip-with-dashes>.sslip.io {
       reverse_proxy 127.0.0.1:<remote-port>
   }
   ```
4. From the presenter's laptop, a **reverse SSH tunnel** opened that local
   port on the VPS and pointed it back at the laptop's own `127.0.0.1:7860`:
   ```
   ssh -i <path-to-key> \
       -N \
       -R 127.0.0.1:<remote-port>:127.0.0.1:7860 \
       -o ServerAliveInterval=15 \
       -o ServerAliveCountMax=3 \
       -o ExitOnForwardFailure=yes \
       <user>@<vps-ip>
   ```
   The forwarded port was bound to `127.0.0.1` **on the VPS**, not
   `0.0.0.0` — so it was only reachable through Caddy's HTTPS front door,
   never directly.
5. While that SSH session stayed open, `https://demo.<ip-with-dashes>.sslip.io`
   resolved to the laptop's Gradio app, with a valid HTTPS certificate, from
   anywhere on the internet. Groupmates opened that one link on their
   phones; the presenter picked each phone from the camera dropdown in the
   Gradio UI and showed it live on the shared screen.
6. As soon as the SSH session was closed, the tunnel disappeared and the
   URL stopped resolving to anything — nothing was left running after the
   demo.

A short wrapper script kept the `ssh` command above alive and reconnected
it automatically if the connection dropped (keepalives +
`ExitOnForwardFailure=yes` so a dead tunnel fails fast and retries,
instead of hanging silently).

## Security notes

- While the tunnel was open, the URL was reachable by **anyone on the
  internet** who had the link — there was no authentication in front of
  it. It was shared only in the Google Meet chat for the session, not
  posted anywhere more permanent.
- The VPS only exposed one new hostname/port for this; nothing else on
  that box was touched.
- The forwarded port was always bound to loopback (`127.0.0.1`) on the
  VPS side, never to all interfaces, so it could not be reached except
  through Caddy's HTTPS proxy.

## Troubleshooting notes (for next time)

- **502 Bad Gateway** from the hostname means Caddy can reach the VPS but
  nothing is listening on the forwarded port there — the SSH tunnel isn't
  up, or the local Gradio app isn't running on `127.0.0.1:7860`. Start the
  Gradio app first, then the tunnel.
- **Certificate warnings** usually mean the hostname was just visited for
  the first time and Caddy is still obtaining the certificate — wait a few
  seconds and reload.
- **Tunnel drops mid-call**: the reconnect loop/keepalives should recover
  it within a few seconds; if not, check the presenter's own network
  connection.
