# 🏆 XAU Bot — Complete Setup Guide
### From Zero to iPhone-Controlled Gold Trading Bot

---

> **Think of it like this:** You have a robot that trades gold for you on a computer far away (a VPS). Your iPhone is the remote control. This guide teaches you how to set up the robot, the computer, and the remote control — step by step, no experience needed.

---

## 📋 Table of Contents

1. [What You Need Before Starting](#1-what-you-need-before-starting)
2. [Understanding the Big Picture](#2-understanding-the-big-picture)
3. [Step 1 — Rent a VPS (Your Remote Computer)](#3-step-1--rent-a-vps-your-remote-computer)
4. [Step 2 — Connect to Your VPS](#4-step-2--connect-to-your-vps)
5. [Step 3 — Upload the Bot to Your VPS](#5-step-3--upload-the-bot-to-your-vps)
6. [Step 4 — Run the Automatic Setup Script](#6-step-4--run-the-automatic-setup-script)
7. [Step 5 — Configure Your Bot Settings](#7-step-5--configure-your-bot-settings)
8. [Step 6 — Build the iPhone App in Xcode](#8-step-6--build-the-iphone-app-in-xcode)
9. [Step 7 — Connect the iPhone App to Your VPS](#9-step-7--connect-the-iphone-app-to-your-vps)
10. [Step 8 — Set Up Push Notifications (Optional)](#10-step-8--set-up-push-notifications-optional)
11. [Step 9 — Start Trading!](#11-step-9--start-trading)
12. [Using the iPhone App — Every Screen Explained](#12-using-the-iphone-app--every-screen-explained)
13. [Understanding the Bot Settings](#13-understanding-the-bot-settings)
14. [The Self-Learning Engine](#14-the-self-learning-engine)
15. [Keeping Everything Updated](#15-keeping-everything-updated)
16. [Troubleshooting — When Things Go Wrong](#16-troubleshooting--when-things-go-wrong)
17. [Security Tips](#17-security-tips)
18. [Glossary — Words You Might Not Know](#18-glossary--words-you-might-not-know)

---

## 1. What You Need Before Starting

Think of this as your shopping list. You need all of these before you can start.

### Things You Must Have

| What | Why You Need It | Cost |
|------|----------------|------|
| **A Mac computer** | To build the iPhone app in Xcode | You already have one |
| **An iPhone** (iOS 17 or newer) | Your remote control for the bot | You already have one |
| **An Apple Developer Account** | To install the app on your phone | $99/year at developer.apple.com |
| **A VPS (cloud server)** | The computer that runs the bot 24/7 | ~$10–$20/month |
| **A broker account** | Where the actual trades happen (MetaTrader 5 compatible) | Free to open |
| **Xcode** (version 15 or newer) | Free app on your Mac to build iPhone apps | Free from Mac App Store |

### Checking Your iPhone Version
1. Open **Settings** on your iPhone
2. Tap **General**
3. Tap **About**
4. Look at **iOS Version** — it must say **17** or higher

### Checking Your Xcode Version
1. Open **Xcode** on your Mac
2. Click **Xcode** in the top menu bar
3. Click **About Xcode**
4. It must say **Version 15** or higher

---

## 2. Understanding the Big Picture

Before touching anything, let's understand what we're building. Imagine three toys that talk to each other:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   📱 YOUR iPHONE          🖥️ VPS SERVER          🏦 BROKER  │
│   (Your Remote)    ←→    (The Robot)      ←→    (The Bank) │
│                                                             │
│   You tap buttons         Runs 24/7                        │
│   See charts              Analyzes gold                    │
│   Get alerts              Places trades                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**The VPS Server** is like a computer you rent in a data center. It never turns off, never sleeps, and runs the trading bot all day and night even when you're asleep.

**The iPhone App** is like a TV remote. It talks to the VPS over the internet and lets you see what's happening, start/stop the bot, and change settings.

**The Broker** is where real money and real trades live. The bot connects to your broker's server (MetaTrader 5) to place and manage trades.

---

## 3. Step 1 — Rent a VPS (Your Remote Computer)

A VPS (Virtual Private Server) is a computer you rent by the month. It lives in a data center and runs 24/7.

### Recommended VPS Providers

| Provider | Plan to Choose | Monthly Price | Why Good |
|----------|---------------|---------------|----------|
| **Contabo** | VPS S | ~$7/month | Cheap, reliable |
| **DigitalOcean** | Basic Droplet (2GB) | ~$12/month | Easy to use |
| **Vultr** | Cloud Compute (2GB) | ~$12/month | Fast setup |
| **Hetzner** | CX22 | ~$5/month | Best value in Europe |

### What to Select When Signing Up

When creating your VPS, choose these exact settings:

- **Operating System:** Ubuntu 22.04 LTS (this is the version the setup script was written for)
- **RAM:** At least **2 GB** (4 GB is better)
- **CPU:** At least **1 vCPU** (2 is better)
- **Storage:** At least **20 GB** SSD
- **Location:** Choose the server closest to your broker's server city for fastest execution

### After You Create the VPS

You will receive an email with:
- **IP Address** — looks like `123.456.78.90` — write this down!
- **Username** — usually `root`
- **Password** — a random string — write this down!

---

## 4. Step 2 — Connect to Your VPS

Connecting to your VPS is like using a very basic text-only window into that remote computer.

### On a Mac (Using Terminal)

1. Open **Terminal** on your Mac
   - Press `Command + Space`, type `Terminal`, press Enter

2. Type this command (replace `123.456.78.90` with your actual IP address):
   ```bash
   ssh root@123.456.78.90
   ```

3. Press **Enter**

4. It will ask:
   ```
   Are you sure you want to continue connecting? (yes/no)
   ```
   Type `yes` and press **Enter**

5. It will ask for your password. Type the password from your email.
   > **Note:** When typing your password, you won't see any letters appear — that's normal! It's hidden for security. Just type it and press Enter.

6. You should now see something like:
   ```
   root@vps-123456:~#
   ```
   This means you're now "inside" your remote VPS computer. 🎉

### Create a Safer User (Important Security Step)

Running everything as `root` is like running with scissors. Let's create a safer user:

```bash
# Create a new user (replace 'botuser' with any name you like)
adduser botuser

# Give it admin powers
usermod -aG sudo botuser

# Switch to that user
su - botuser
```

It will ask you to create a password for `botuser` — make it strong!

---

## 5. Step 3 — Upload the Bot to Your VPS

Now we need to get the bot's code onto your VPS.

### Option A — Download from GitHub (Easiest)

Still in your VPS terminal, type these commands one by one, pressing Enter after each:

```bash
# Install git (a tool for downloading code)
sudo apt update && sudo apt install -y git

# Download the bot code
git clone https://github.com/m0hd1121/xau_bot.git

# Go into the folder (it will be called xau_bot — all lowercase)
cd xau_bot

# Check you're on the right version
git checkout claude/xauusd-price-action-bot-T80IJ
```

> **Note:** The folder on your VPS will be called `xau_bot` (lowercase). That's fine — the setup script automatically detects where it lives, so the name doesn't matter.

### Option B — Upload from Your Mac (Alternative)

If you prefer uploading from your Mac, open a **new Terminal window on your Mac** (not the VPS one) and type:

```bash
scp -r /path/to/XAU_Bot root@123.456.78.90:/home/botuser/
```

Replace `/path/to/XAU_Bot` with where the folder is on your Mac, and `123.456.78.90` with your VPS IP.

---

## 6. Step 4 — Run the Automatic Setup Script

This is the magic step. We wrote a script that does all the complicated setup automatically — like having a robot set up your new computer for you.

### What the Script Does (So You Know)

The setup script automatically:
- Installs Python and all required libraries
- Creates a secure virtual environment for the bot
- Generates random secret keys for security (so nobody can guess them)
- Creates a self-signed SSL certificate (so your connection is encrypted)
- Sets up the firewall (blocks dangerous ports, allows only what's needed)
- Creates the admin account for the iPhone app
- Installs and starts the bot and API as background services
- Makes them auto-restart if the server reboots

### Running the Script

In your VPS terminal, make sure you're in the `xau_bot` folder:

```bash
# Go to the right folder (if not already there)
cd ~/xau_bot

# Make the script executable (give it permission to run)
chmod +x backend/scripts/setup.sh

# Run it!
sudo bash backend/scripts/setup.sh
```

> ⏰ **This takes about 3–5 minutes.** You'll see a lot of text scrolling — that's normal. Don't close the terminal!

### After the Script Finishes

At the end, you'll see something like:

```
============================================================
  XAU Bot API Setup Complete!
============================================================
  API URL:      https://123.456.78.90:8443
  Admin user:   admin
  Admin pass:   (check /home/botuser/xau_bot/.env)
============================================================
```

**Write down the API URL!** You'll need it when setting up the iPhone app.

To see your admin password:
```bash
cat ~/xau_bot/.env | grep ADMIN_PASSWORD
```

Write this down too — you need it to log into the iPhone app.

---

## 7. Step 5 — Configure Your Bot Settings

The bot's brain is controlled by a file called `config.yaml`. Think of it as the bot's instruction manual.

### Open the Config File

```bash
nano ~/xau_bot/config.yaml
```

This opens a simple text editor right in the terminal.

> **How to use nano:** 
> - Arrow keys to move around
> - Type to change values
> - `Ctrl + S` to save
> - `Ctrl + X` to exit

### The Most Important Settings to Change

```yaml
bot:
  mode: "paper"   # ← CHANGE THIS FIRST
                  # "backtest" = test on old data (safe, no real money)
                  # "paper"    = pretend trading with fake money (safe)
                  # "live"     = real trading with real money (be careful!)
```

> 🚨 **IMPORTANT:** Always start with `"paper"` mode. Only switch to `"live"` after you've tested for weeks and are confident the bot is working correctly. Real money is real!

```yaml
risk:
  initial_capital: 10000.0    # ← Your starting account balance in USD
  risk_per_trade: 0.01        # ← Risk 1% per trade (0.01 = 1%)
                              #   Never set this above 0.02 (2%) when starting!
  daily_loss_limit: 0.03      # ← Stop trading for the day if you lose 3%
  max_drawdown_kill: 0.10     # ← Emergency stop if account drops 10%
```

```yaml
data:
  source: "mt5"               # ← Use "mt5" for live/paper, "csv" for backtest
  mt5_server: "YourBroker-Server"  # ← Your broker's MT5 server name
  mt5_login: 12345678              # ← Your MT5 account number
  mt5_password: "YourPassword"     # ← Your MT5 account password
```

> 💡 **Finding your MT5 server name:** Open MetaTrader 5 on your computer, go to File → Open an Account, and look at the list of servers.

After making your changes, save with `Ctrl + S` then exit with `Ctrl + X`.

Restart the bot to apply changes:
```bash
sudo systemctl restart xaubot-bot
sudo systemctl restart xaubot-api
```

---

## 8. Step 6 — Build the iPhone App in Xcode

Now we build the iPhone app on your Mac. Think of Xcode as a factory that turns our code into an iPhone app.

### Step 6.1 — Open the Project in Xcode

1. Open **Finder** on your Mac
2. Navigate to the `XAU_Bot` folder
3. Go into the `iOS` folder
4. You'll see a folder called `XAUBot` — this is the source code

**Create a new Xcode project:**

1. Open **Xcode**
2. Click **Create New Project**
3. Select **iOS** → **App**
4. Click **Next**
5. Fill in the details:
   - **Product Name:** `XAUBot`
   - **Team:** Select your Apple Developer account
   - **Organization Identifier:** `com.yourname` (e.g., `com.johndoe`)
   - **Bundle Identifier:** Will auto-fill as `com.yourname.XAUBot`
   - **Interface:** `SwiftUI`
   - **Language:** `Swift`
   - **Minimum Deployments:** `iOS 17.0`
6. Click **Next**
7. Save it somewhere on your Mac
8. Click **Create**

### Step 6.2 — Add the Source Files

Now we add all the Swift files we wrote:

1. In Xcode, right-click on the `XAUBot` folder in the left sidebar
2. Select **Add Files to "XAUBot"...**
3. Navigate to `XAU_Bot/iOS/XAUBot/`
4. Select **all the folders** inside it (App, Authentication, Backup, etc.)
5. Make sure **"Copy items if needed"** is checked
6. Make sure **"Create groups"** is selected
7. Click **Add**

### Step 6.3 — Add the Swift Charts Framework

The analytics charts require Swift Charts, which is built into iOS 16+, so nothing extra needed — it's already there!

### Step 6.4 — Set Up Signing

1. Click on the **XAUBot** project name at the very top of the left sidebar (the blue icon)
2. Click on the **XAUBot** target
3. Click the **Signing & Capabilities** tab
4. Make sure **Automatically manage signing** is checked
5. Under **Team**, select your Apple Developer account

### Step 6.5 — Build and Install on Your iPhone

1. Plug your iPhone into your Mac with a USB cable
2. In Xcode, click the device selector at the top (it might say "iPhone" or an iPhone model name)
3. Select your iPhone from the list
4. Click the **▶️ Play button** (top left) to build and install
5. The first time, your iPhone will say **"Untrusted Developer"**:
   - On your iPhone: Go to **Settings → General → VPN & Device Management**
   - Find your developer name and tap **Trust**
6. Open the **XAUBot** app on your iPhone

---

## 9. Step 7 — Connect the iPhone App to Your VPS

When you first open the app, you'll see a login screen. Before logging in, you need to tell the app where your VPS is.

### First Time Setup

1. Open the **XAUBot** app on your iPhone
2. You'll see a login screen with a field at the top that says **"Server URL"**
3. Type your VPS address:
   ```
   https://123.456.78.90:8443
   ```
   (Replace `123.456.78.90` with your actual VPS IP address)
4. In **Username**, type: `admin`
5. In **Password**, type the admin password you wrote down earlier
6. Tap **Sign In**

### If You See a Certificate Warning

Because we used a self-signed SSL certificate (a free one we made ourselves), your iPhone might not trust it at first. Here's how to fix it:

**Option A — Trust on iPhone (Easier but less secure):**
1. Open **Safari** on your iPhone
2. Go to `https://123.456.78.90:8443/health`
3. Tap **Show Details** → **Visit this website**
4. Tap **Visit Website**
5. Go back to the XAUBot app and try logging in again

**Option B — Use a Real SSL Certificate (Better for long-term):**

On your VPS, run:
```bash
# Install certbot (free SSL certificate tool)
sudo apt install -y certbot

# You need a domain name pointing to your VPS for this
# Replace yourdomain.com with your actual domain
sudo certbot certonly --standalone -d yourdomain.com

# Update the API service to use the new certificate
sudo nano /etc/systemd/system/xaubot-api.service
# Change the --ssl-certfile and --ssl-keyfile lines to point to /etc/letsencrypt/live/yourdomain.com/
```

> 💡 You can get a free domain at freenom.com or buy a cheap one at namecheap.com for ~$1/year.

---

## 10. Step 8 — Set Up Push Notifications (Optional)

Push notifications let your iPhone get alerts even when the app is closed — like getting a text message when the bot opens or closes a trade.

> **This step requires an Apple Developer account ($99/year) and is optional.** The app works fine without it — you just won't get background notifications.

### Step 10.1 — Create an APNs Key

1. Go to [developer.apple.com](https://developer.apple.com)
2. Sign in and go to **Certificates, Identifiers & Profiles**
3. In the left sidebar, click **Keys**
4. Click the **+** button to create a new key
5. Give it a name like `XAUBot APNs Key`
6. Check the box next to **Apple Push Notifications service (APNs)**
7. Click **Continue** → **Register**
8. **Download the `.p8` file** — you can only download it ONCE, so keep it safe!
9. Also note your **Key ID** and **Team ID** (shown on the page)

### Step 10.2 — Upload the Key to Your VPS

On your Mac terminal (not VPS terminal):
```bash
scp ~/Downloads/AuthKey_XXXXXXXXXX.p8 root@123.456.78.90:/home/botuser/xau_bot/backend/
```

### Step 10.3 — Tell the API About Your Key

On your VPS:
```bash
nano ~/xau_bot/.env
```

Find and fill in these lines:
```
APNS_KEY_FILE=/home/botuser/xau_bot/backend/AuthKey_XXXXXXXXXX.p8
APNS_KEY_ID=XXXXXXXXXX
APNS_TEAM_ID=XXXXXXXXXX
APNS_BUNDLE_ID=com.yourname.XAUBot
```

Replace the `XXXXXXXXXX` values with your actual Key ID, Team ID, and the filename of your `.p8` file.

Save and restart:
```bash
source ~/.env
sudo systemctl restart xaubot-api
```

---

## 11. Step 9 — Start Trading!

You're all set up! Here's how to start the bot safely.

### Safe Starting Checklist

Before doing anything with real money, go through this list:

- [ ] Mode is set to `"paper"` in config.yaml
- [ ] You've watched the bot run in paper mode for at least 1–2 weeks
- [ ] The win rate looks reasonable (above 40%)
- [ ] The daily loss limit has never been hit in paper mode
- [ ] You understand every setting in the Configuration screen
- [ ] You have read the risk warnings below

### Starting the Bot from Your iPhone

1. Open the **XAUBot** app
2. Tap the **Dashboard** tab (house icon)
3. Tap the **More** tab (three dots at bottom right)
4. Tap **Bot Control**
5. Tap the big green **Start Bot** button
6. A confirmation message will appear — read it and tap **Confirm**

You'll see the status change from "Stopped" to "Running" on your dashboard.

### 🚨 Risk Warnings — Please Read

- **Never invest money you cannot afford to lose.** Trading involves real risk.
- **Start with paper trading.** Run the bot with fake money first to see how it behaves.
- **Start with small risk.** Keep `risk_per_trade` at 0.01 (1%) or less when you start live trading.
- **Monitor daily.** Check the dashboard every day, especially in the first month.
- **The bot can lose money.** No trading bot is perfect. Past performance does not guarantee future results.

---

## 12. Using the iPhone App — Every Screen Explained

### 🏠 Dashboard Tab

This is your home screen. It shows you everything happening right now.

**What you see:**
- **Bot Status** — A colored dot and text:
  - 🟢 Green "Running" = Bot is working normally
  - 🟡 Yellow "Paused" = Bot is paused (won't open new trades)
  - 🔵 Blue "Maintenance" = Maintenance mode, no trading
  - 🔴 Red "Emergency Stop" = Manually stopped for safety
  - ⚫ Grey "Stopped" = Bot is not running

- **Balance** — Your account's total cash value
- **Equity** — Balance + unrealized profit/loss from open trades
- **Daily P&L** — How much you've made or lost today
- **Open Trades** — How many trades are currently open

**Pull down to refresh** (drag down from top) if data looks old.

---

### ↔️ Trades Tab

Shows all your trades — both open (current) and past (history).

**Live subtab:**
- Each card shows one open trade
- **Direction badge:** Green "BUY" or Red "SELL"
- **P&L number:** Green means profit, red means loss
- **Swipe left** on a trade to see the Close button

**History subtab:**
- List of every closed trade ever
- Use the filter chips to show only wins, losses, or specific sessions
- Tap any trade to see full details including the AI explanation

---

### 📈 Analytics Tab

Charts and statistics about the bot's performance.

**Overview:** Big numbers — win rate, profit factor, best/worst trade.

**Charts:**
- **Equity Curve** — A line showing how your account value has changed over time. You want this to go up!
- **Drawdown** — Shows how far the account has dropped from its peak. Smaller is better.
- **Daily Returns** — Bars showing profit/loss each day. Green = profit day, red = loss day.

**Sessions:** Which trading session (London, New York) performs best for your bot.

**Regimes:** How the bot performs in different market conditions (trending, ranging, volatile).

---

### 🧠 Learning Tab

This shows the self-learning engine's progress.

- **Trades Analyzed** — How many trades the AI has studied
- **Validation status** — Whether the AI's learned patterns have been verified as genuinely useful (not just random luck)
- **Patterns** — Specific setups the AI has found work better or worse
- **Confidence chart** — How confident the AI is in its setups over time

> 💡 The learning engine needs at least 30 trades before it starts having an effect. It's like a student who needs to study before they can help.

---

### ⋯ More Tab

This is where all the control panels live.

**Bot Control:**
- **Start/Stop/Restart** — Turn the bot on, off, or restart it
- **Pause** — Temporarily stop opening new trades (closes nothing)
- **Resume** — Unpause
- **Emergency Stop** — Immediately stop everything (use only in emergencies)
- **Maintenance Mode** — Special mode for updates, no trading happens

> 🚨 Every button in Bot Control shows a **confirmation dialog** before doing anything. Always read it before tapping Confirm.

**Configuration:**
- Edit all the bot's settings from your phone
- Each section has a **Save** and **Discard** button — you must tap Save for changes to apply

**VPS Monitor:**
- See if your server is healthy
- CPU, RAM, and disk usage gauges
- List of running services with restart buttons

**Logs:**
- Real-time text logs from the bot
- Filter by log level (Info, Warning, Error, etc.)
- Search for specific text

**Backup:**
- Create a backup of all bot data and settings
- Restore from a previous backup
- Export trade history as a CSV file (opens in Excel/Numbers)

**Trading Account:**
- View your broker account details
- Balance, equity, margin usage
- Add or remove broker accounts

**Notifications:**
- Turn on/off push notifications for specific events
- Set drawdown warning thresholds

**Settings:**
- Change your login password
- Set up 2FA (two-factor authentication for extra security)
- Enable Face ID / Touch ID login
- Change the server URL if your VPS IP changes

---

## 13. Understanding the Bot Settings

Here's what each setting in `config.yaml` actually means, explained simply.

### Risk Settings

```yaml
risk:
  initial_capital: 10000.0
```
> **What it means:** Tell the bot how much money is in your account. This is just for calculation purposes — the bot can't add or remove money from your account on its own.

```yaml
  risk_per_trade: 0.01
```
> **What it means:** On each trade, the bot risks 1% of your account. If you have $10,000, it risks $100 per trade. **Never set above 0.02** (2%) — higher than that and a losing streak will destroy your account quickly.

```yaml
  daily_loss_limit: 0.03
```
> **What it means:** If you lose 3% in one day, the bot stops trading for the rest of that day. Like having a rule that says "after 3 bad plays, take a break."

```yaml
  max_drawdown_kill: 0.10
```
> **What it means:** If the account ever drops 10% below its peak value, the bot completely stops and requires you to manually restart it. This is your safety net.

```yaml
  min_reward_to_risk: 2.0
```
> **What it means:** The bot will only take a trade if it expects to make at least 2x what it risks. If it risks $100, it won't enter unless it thinks it can make $200.

### Strategy Settings

```yaml
strategy:
  require_htf_bias: true
```
> **What it means:** Only trade in the same direction as the overall 4-hour chart trend. Like only swimming with the current, not against it.

```yaml
  require_session_window: true
```
> **What it means:** Only trade during active market hours (London and New York sessions). Don't trade at 3am when markets are quiet and spreads are wide.

```yaml
  tp1_rr: 1.5
  tp2_rr: 3.0
```
> **What it means:** Close half the trade at 1.5× profit (TP1) and let the other half run to 3× profit (TP2). This locks in some profit while still letting winners run.

```yaml
  use_break_even: true
```
> **What it means:** Once TP1 is hit, move the stop loss to your entry price. This means the trade can never turn into a loss — worst case you break even.

### Psychology Settings

```yaml
psychology:
  max_consecutive_losses: 3
```
> **What it means:** After 3 losses in a row, reduce trade size by 50% temporarily. This prevents the bot from "revenge trading" — trying to win back losses by betting bigger.

```yaml
  cooldown_candles_after_loss: 3
```
> **What it means:** Wait 3 candles (3 hours if trading 1H) after a loss before entering again. Time to breathe and let the market settle.

---

## 14. The Self-Learning Engine

The learning engine is like a student that studies every trade the bot makes and tries to figure out what works and what doesn't.

### How It Works (Simple Version)

1. **Bot takes a trade** → Learning engine records everything about that trade (market conditions, time of day, candle patterns, etc.)
2. **Trade closes** → Learning engine records whether it won or lost
3. **After 50 trades** → Learning engine analyzes all the data to find patterns
4. **After finding patterns** → Learning engine adjusts how confident it is about similar setups in the future
5. **Validation** → Before using any learned pattern, it checks the pattern on data it hasn't seen before to make sure it's real, not just luck

### What the Learning Engine Will NEVER Do

> These are hard rules that cannot be changed by the learning process:
> - ❌ Remove stop losses from trades
> - ❌ Increase your risk per trade
> - ❌ Ignore the daily loss limit
> - ❌ Ignore the drawdown kill switch
> - ❌ Chase losses by taking worse setups
> - ❌ Optimize only for winning more trades at the cost of losing more money

### Enabling It

By default, learning is disabled. To enable:
1. Open the app → **More → Configuration**
2. Tap the **Learning** section
3. Toggle **Enable Learning** to ON
4. Tap **Save**

---

## 15. Keeping Everything Updated

### Updating the Bot Code

When a new version is available:

```bash
# Connect to your VPS
ssh botuser@123.456.78.90

# Go to the bot folder
cd ~/xau_bot

# Download the latest code
git pull origin claude/xauusd-price-action-bot-T80IJ

# Install any new requirements
source venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Restart everything
sudo systemctl restart xaubot-bot
sudo systemctl restart xaubot-api
```

### Updating the iPhone App

If you update the code, you need to rebuild and reinstall:
1. Pull the latest code to your Mac
2. Open the project in Xcode
3. Click the Play button to rebuild and install

### Automatic Updates (Optional)

The `backend/scripts/deploy.sh` script does all the above automatically:
```bash
sudo bash ~/xau_bot/backend/scripts/deploy.sh
```

---

## 16. Troubleshooting — When Things Go Wrong

### "Cannot Connect to Server" in the App

**Check 1 — Is the API running?**
```bash
sudo systemctl status xaubot-api
```
If it says `inactive` or `failed`, restart it:
```bash
sudo systemctl restart xaubot-api
```

**Check 2 — Is the URL correct?**
- In the app: More → Settings → Server URL
- Make sure it starts with `https://`
- Make sure the port `:8443` is at the end
- Make sure there's no space or typo

**Check 3 — Is the firewall blocking you?**
```bash
sudo ufw status
```
You should see port `8443` listed as `ALLOW`. If not:
```bash
sudo ufw allow 8443/tcp
sudo ufw reload
```

---

### "No such file or directory: requirements.txt" During Setup

This means the setup script couldn't find the project files — usually because the cloned folder name didn't match what the old script expected.

The updated setup script fixes this by auto-detecting its location. Pull the latest version and re-run:

```bash
cd ~/xau_bot   # or whatever folder you cloned into
git pull origin claude/xauusd-price-action-bot-T80IJ
sudo bash backend/scripts/setup.sh
```

If you're still getting the error, check that you're running the script from inside the project folder and that the `backend/` directory exists:
```bash
ls ~/xau_bot/backend/
# You should see: app/ scripts/ systemd/ requirements.txt .env (etc.)
```

---

### "python3.11: command not found" During Setup

This means your Ubuntu version doesn't have Python 3.11 in its default package list. The updated setup script handles this automatically by trying Python 3.11, then falling back to whatever Python 3.10+ is available.

If you already got this error, run these commands to fix it and re-run setup:

```bash
# Option A — Install Python 3.11 from the deadsnakes PPA (recommended)
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# Then re-run setup
sudo bash backend/scripts/setup.sh
```

```bash
# Option B — Use Python 3.10 (already on Ubuntu 22.04)
# The updated setup.sh detects this automatically.
# Just re-run setup with the latest script:
git pull origin claude/xauusd-price-action-bot-T80IJ
sudo bash backend/scripts/setup.sh
```

---

### "Bot Won't Start"

**Check the bot's status:**
```bash
sudo systemctl status xaubot-bot
```

**See what error occurred:**
```bash
sudo journalctl -u xaubot-bot -n 50
```

**Common fixes:**
- If the error mentions Python: `source ~/xau_bot/venv/bin/activate && pip install -r requirements.txt`
- If the error mentions the config file: Make sure your `config.yaml` changes are valid (no typos)
- If the error mentions the broker: Check your MT5 server, login, and password in `config.yaml`

---

### "App Shows 'Disconnected' Banner"

This is the yellow banner at the top saying "Disconnected." It means the WebSocket live connection was lost.

- **This is usually temporary** — the app reconnects automatically within 30 seconds
- If it doesn't reconnect, check that the API is running (see above)
- Try logging out and back in

---

### "No Trades Being Placed"

The bot is running but not taking any trades. This is usually normal — the bot is picky and will only trade when conditions are perfect.

**Check these things:**
1. Is the mode set to something other than `"backtest"`?
   ```bash
   grep "mode:" ~/xau_bot/config.yaml
   ```

2. Are you in an active session window? (London: 07:00–12:00 UTC, New York: 13:00–17:00 UTC)

3. Is the daily loss limit already hit today?
   - Check the Dashboard — does it say "Daily Loss Limit Reached"?

4. Has the bot been in a loss streak?
   - Check Psychology settings — it might be in cooldown

5. Is market volatility too low or too high?
   - The bot won't trade in very thin Asian session markets by default

---

### "I Forgot My Password"

On your VPS:
```bash
# See the current password
cat ~/xau_bot/.env | grep ADMIN_PASSWORD

# Or reset it
cd ~/xau_bot
source venv/bin/activate
python -c "
from backend.app.auth.security import hash_password
print(hash_password('YourNewPassword123!'))
"
```

Then update the database:
```bash
sqlite3 ~/xau_bot/data/api.db "UPDATE users SET hashed_password='PASTE_HASH_HERE' WHERE username='admin';"
```

---

### VPS Ran Out of Disk Space

```bash
# Check disk usage
df -h

# See what's taking up space
du -sh ~/xau_bot/logs/*

# Clean up old logs (keeps last 7 days)
find ~/xau_bot/logs -name "*.log" -mtime +7 -delete
```

---

### Everything is Broken — Nuclear Option

If all else fails, re-run the setup script. It's safe to run again:
```bash
sudo bash ~/xau_bot/backend/scripts/setup.sh
```

---

## 17. Security Tips

Your bot handles real money — security matters. Here are the most important steps:

### Must Do

- ✅ **Use a strong password** — At least 12 characters, mix of letters, numbers, symbols
- ✅ **Enable 2FA** — In the app: More → Settings → Enable 2FA. This means even if someone gets your password, they can't log in without your phone.
- ✅ **Enable Face ID / Touch ID** — In the app: More → Settings → Biometric Login
- ✅ **Keep your API URL private** — Don't share it. Don't post it on social media.
- ✅ **Backup regularly** — In the app: More → Backup → Create Backup. Do this weekly.

### Good to Do

- 🔒 **Change the default admin password** right after first login
- 🔒 **Use a domain name** instead of raw IP address — harder for scanners to find
- 🔒 **Set up SSH key authentication** on your VPS (so hackers can't brute-force the password)
- 🔒 **Check the VPS logs weekly** for any suspicious activity

### Never Do

- ❌ Never share your `.env` file with anyone
- ❌ Never post your JWT secrets online
- ❌ Never use the same password for the bot app and your broker
- ❌ Never enable the API on port 80 or 443 without proper SSL

---

## 18. Glossary — Words You Might Not Know

| Word | What It Means in Simple Terms |
|------|-------------------------------|
| **VPS** | A computer you rent in a data center that runs 24/7 |
| **SSH** | A secure way to control your VPS from your computer's terminal |
| **API** | A way for the iPhone app to talk to the bot on the VPS |
| **JWT** | A digital "ticket" that proves you're logged in |
| **2FA/TOTP** | A second password that changes every 30 seconds (like Google Authenticator) |
| **WebSocket** | A live connection so the app updates in real time without refreshing |
| **APNs** | Apple's system for sending push notifications to iPhones |
| **SSL/TLS** | Encryption that makes your connection secure (the padlock icon) |
| **P&L** | Profit and Loss — how much money you've made or lost |
| **Equity** | Your account balance including any currently open trade profits/losses |
| **Drawdown** | How much your account has fallen from its highest point |
| **R (Risk Multiple)** | If you risk $100 and make $200, that's 2R profit |
| **BOS** | Break of Structure — when price breaks past a significant swing point |
| **CHoCH** | Change of Character — when the trend changes direction |
| **OB / Order Block** | A zone on the chart where big banks placed their orders |
| **Liquidity Sweep** | When price briefly passes a key level to grab stop losses before reversing |
| **HTF** | Higher Time Frame — a longer chart like the 4-hour or daily |
| **LTF** | Lower Time Frame — a shorter chart like the 1-hour or 15-minute |
| **Spread** | The difference between buy and sell price, paid to the broker |
| **Lot** | A unit of trade size. 1 standard lot = 100 oz of gold |
| **SL / Stop Loss** | A price level where the trade automatically closes to limit your loss |
| **TP / Take Profit** | A price level where the trade automatically closes to lock in your profit |
| **Break-Even** | Moving the stop loss to your entry price so the worst outcome is no loss |
| **Backtesting** | Testing the bot on historical price data to see how it would have performed |
| **Paper Trading** | Simulated trading with fake money to test without real risk |
| **Win Rate** | Percentage of trades that are profitable |
| **Profit Factor** | Total profits divided by total losses. Above 1 = profitable overall |
| **Expectancy** | Average profit/loss per trade. Positive = good, negative = bad |
| **Regime** | The current market condition (trending, ranging, volatile) |
| **systemd** | Linux's system for running background services that auto-restart |
| **pip** | Python's package manager (like an App Store for Python libraries) |
| **venv** | A virtual environment — an isolated space for the bot's Python packages |

---

## 📞 Getting Help

If you're stuck and this guide doesn't solve your problem:

1. **Check the logs first** — In the app: More → Logs → change type to "api" and look for red ERROR messages
2. **Look at the VPS logs:**
   ```bash
   sudo journalctl -u xaubot-api -n 100
   sudo journalctl -u xaubot-bot -n 100
   ```
3. **Open a GitHub Issue** at the repository page with:
   - What you were trying to do
   - What happened instead
   - The error message (if any)
   - Your VPS OS version: `lsb_release -a`
   - Your Python version: `python3 --version`

---

*Good luck with your trading! Remember: slow and steady wins the race. Start in paper mode, watch and learn, then go live carefully.* 🏆
