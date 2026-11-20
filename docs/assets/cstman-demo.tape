# CSTMAN demo — reproducible hero gif for the README.
# Render:  cd <repo root> && PATH=/opt/homebrew/bin:$PATH vhs docs/assets/cstman-demo.tape
# Produces: docs/assets/cstman-demo.gif  (runs the REAL engine on the committed sample)

Output docs/assets/cstman-demo.gif
Require go

Set Shell bash
Set FontFamily "Menlo"
Set FontSize 24
Set Width 1180
Set Height 420
Set Padding 36
Set Theme "Catppuccin Mocha"
Set TypingSpeed 55ms

# --- off-screen setup: build the real engine, stage the sample as orders.json,
#     alias `cstman` to the reproducible wrapper ---
Hide
Type "go build -o /tmp/cstman-engine ./public/engine/cmd/cstman-engine" Enter
Sleep 5s
Type "cp docs/assets/cstman-demo.sample.json orders.json" Enter
Type "cstman() { CSTMAN_BIN=/tmp/cstman-engine docs/assets/cstman-demo.sh; }" Enter
Type "clear" Enter
Show

Sleep 800ms
Type "cstman compress < orders.json"
Sleep 700ms
Enter
Sleep 3s
Sleep 1500ms
