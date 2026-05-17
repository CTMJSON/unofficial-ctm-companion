# Unofficial CTM Companion — macOS App

A beautiful, native macOS application that brings powerful CTM analytics tools to your desktop. Run advanced CTM reports and analyses with a single click, all with a professional interface and secure credential management.

![CTM Companion](https://img.shields.io/badge/macOS-14.0+-blue)
![Version](https://img.shields.io/badge/version-1.0-brightgreen)
![License](https://img.shields.io/badge/license-proprietary-red)

---

## 📋 What's Inside

CTM Companion integrates **7 powerful tools** directly into your macOS:

### Analysis Tools (6)
| Tool | Purpose | Output |
|------|---------|--------|
| **Account Assessment** | Full health report of your CTM account with KPIs and detailed metrics | HTML + 7 CSV files |
| **One-Pager** | Executive-friendly summary report with key metrics and trends | Single HTML report |
| **Daily Summary** | Daily KPI dashboard with agent scorecards and performance metrics | HTML + 4 CSV files |
| **AskAI Enhancer** | Optimize and improve your AI prompts using ChatGPT | Markdown + CSV |
| **Q&A Report** | Extract and analyze call transcripts and Q&A pairs | HTML report |
| **VoiceAI Analyzer** | Analyze voice quality and AI performance metrics | CSV data |

### Communication Tool (1)
| Tool | Purpose | Features |
|------|---------|----------|
| **CTM Softphone** | Embedded phone interface with call logs and click-to-call | Live activity logs, auto-dialing, account management |

All tools run **locally on your machine** with your credentials stored securely in macOS Keychain.

---

## 🚀 Getting Started

### System Requirements

- **macOS**: 14.0 (Sonoma) or later
- **RAM**: 256 MB minimum (typically uses 50-100 MB)
- **Disk Space**: 100 MB for app + Python environment
- **Python**: Auto-detected (Homebrew or system Python 3)
- **Internet**: Required for CTM API and OpenAI API calls

### Installation (2 minutes)

1. **Download** the latest DMG from [Releases](https://github.com/CTMJSON/ctm-companion/releases)

2. **Mount** the DMG:
   - Double-click `CTMCompanion-1.0.dmg`
   - The volume opens in Finder

3. **Install** the app:
   - Drag **CTM Companion.app** to the **Applications** folder
   - This copies the app to your system

4. **Launch** the app:
   - Open **Applications** folder
   - Double-click **CTM Companion**
   - If prompted "Cannot be verified": Open **System Settings** → **Security & Privacy** → Click **Open Anyway**
   - Grant notification permissions when asked

5. **Configure** credentials (one-time setup):
   - Press **Cmd+,** to open Settings
   - Click **Credentials** tab
   - Enter your CTM Basic Auth Token
   - Enter your default Account ID
   - Optionally add OpenAI API Key for AI tools
   - Click outside the field to save (no button needed)
   - Look for green checkmarks ✓

6. **Start using**:
   - Select a tool from the sidebar
   - Fill in any parameters (dates, filters, etc.)
   - Click **"Run Tool"** or press **Cmd+R**
   - Watch output stream in real-time
   - Results open automatically in your browser

**That's it!** You're ready to run your first report.

---

## 🎯 How to Use Each Tool

### 1. Account Assessment
Get a comprehensive health report of your entire CTM account.

**Steps:**
1. Click "Account Assessment" in sidebar
2. Select **Start Date** and **End Date** (defaults to last 30 days)
3. Click **Run Tool**
4. Report opens in browser automatically
5. All output files saved to `~/Documents/CTM Companion/account-assessment/`

**Output includes:**
- Account health score and trends
- Call volume and type breakdown
- Agent performance scorecards
- Lead source analysis
- 7 detailed CSV files for deeper analysis

---

### 2. Account Assessment One-Pager
Perfect for executive summaries or quick reviews.

**Steps:**
1. Click "Account Assessment (One-Pager)"
2. Choose date range
3. Click **Run Tool**
4. Single-page HTML report opens instantly

**Best for:** Sharing with management, board meetings, quick reviews

---

### 3. Daily Executive Summary
Monitor daily performance with KPI dashboards.

**Steps:**
1. Click "Daily Executive Summary"
2. Select the **date** (defaults to today)
3. Optional: Set **calls limit** (default: all calls)
4. Click **Run Tool**

**Includes:**
- Daily KPI metrics (calls, conversions, avg duration)
- Agent-by-agent scorecards
- Hourly trends
- Performance comparisons to historical data

---

### 4. AskAI Prompt Enhancer
Improve your AI prompts using ChatGPT (requires OpenAI API key).

**Steps:**
1. Click "AskAI Prompt Enhancer"
2. Paste or type your current prompt in the text box
3. Click **Run Tool**
4. Get optimized prompt suggestions
5. Results include original + enhanced versions

**Use cases:**
- Improve IVR prompts
- Refine chatbot instructions
- Optimize voice AI behavior
- A/B test prompt variations

---

### 5. Support Q&A Report
Extract call transcripts and question-answer pairs.

**Steps:**
1. Click "Support Q&A Report"
2. Select **date range**
3. Optional filters:
   - **Agent filter**: Specific agent name
   - **Call type**: Inbound/outbound
4. Click **Run Tool**
5. HTML report opens with structured Q&A data

**Output includes:**
- Full call transcripts
- Extracted questions and answers
- Timestamps and agent names
- Downloadable for analysis

---

### 6. VoiceAI Analyzer
Analyze voice quality and AI performance metrics.

**Steps:**
1. Click "VoiceAI Analyzer"
2. Select **date range**
3. Enter Account ID (if different from default)
4. Click **Run Tool**
5. CSV file opens with detailed metrics

**Metrics include:**
- Voice quality scores
- AI response times
- Transcription accuracy
- Agent handoff rates
- Customer satisfaction signals

---

### 7. CTM Softphone
Embedded phone interface for making calls, viewing activity logs, and managing your CTM account directly.

**Setup (One-Time):**
The softphone requires the Flask web app to be running locally. This happens automatically when you click "Run Tool" for the first time.

**Steps:**
1. Click "CTM Softphone" in sidebar
2. Click **Run Tool**
3. Flask server starts automatically (port 8080)
4. Browser opens with embedded softphone interface
5. Log in with your CTM agent credentials
6. Start making calls and managing calls directly from the softphone

**Features:**
- **Embedded Phone Interface**: Make and receive calls without leaving your workspace
- **Live Activity Logs**: See incoming/outgoing calls and texts in real-time
- **Click-to-Call**: Dial directly from logged activity with one click
- **Auto-Refresh**: Logs update every 30 seconds
- **Account Management**: Access CTM settings and features
- **Agent Workspace**: View KPIs and searchable activity filters

**Keeping Softphone Running:**
- The softphone runs as a local web server while in use
- It closes when you stop the tool or close the app
- Open in a separate browser window for best results
- You can leave it running while using other CTM Companion tools

**Note:** The softphone requires the CTM Softphone Flask app, which is included with CTM Companion. If you're missing the softphone files, download them from [Custom CTM Softphone Example](https://github.com/CTMJSON/Custom-CTM-Softphone-Example).

---

## ⚙️ Settings & Configuration

Press **Cmd+,** (Command + Comma) anytime to open Settings. Four tabs available:

### 1. Credentials Tab
**Where to get values:**

- **CTM Basic Auth Token**
  - Go to CTM Settings → API Keys
  - Copy "Basic Auth Token" (format: `username:password` base64)
  
- **Account ID**
  - Go to CTM Account Settings
  - Your account number (usually 2-3 digits)

- **OpenAI API Key** (Optional)
  - Go to https://platform.openai.com/api-keys
  - Create or copy existing key
  - Only needed for AskAI Enhancer

Green checkmarks ✓ indicate credentials are saved and verified.

### 2. Output Tab
- **Output Location**: Where results are saved (default: `~/Documents/CTM Companion/`)
- **Auto-open HTML**: Automatically opens reports in browser after completion
- **Show Notifications**: Desktop alerts when tools complete

### 3. Python Tab
- **Python Detection**: Shows detected Python version and path
- **Venv Location**: Auto-managed Python virtual environment
- **Status**: Shows if environment is properly configured

### 4. History Tab
- **Recent Runs**: View your last 20 tool executions
- **View Results**: Click any run to see output files and logs
- **Clear History**: Remove old runs to clean up

---

## 💡 Tips & Tricks

### Speed Up Reports
- Run during off-peak hours when CTM API is less busy
- Use narrower date ranges for specific analysis
- Run one tool at a time (no parallel execution)

### Organize Results
- Output files are saved by tool and date in `~/Documents/CTM Companion/`
- Export CSVs to Excel for further analysis
- Use History tab to find previous reports quickly

### Keyboard Shortcuts
- **Cmd+R**: Run the current tool (fastest way!)
- **Cmd+,**: Open Settings
- **Click sidebar**: Switch between tools instantly

### Share Results
1. Run a report
2. Find the HTML file in Finder (History tab shows the location)
3. Email the HTML file or share the link
4. Others can open in their browser

---

## 🔒 Security & Privacy

### Your Credentials
- ✅ Stored securely in **macOS Keychain** (encrypted by OS)
- ✅ Never written to disk as plain text
- ✅ Never sent to third-party services
- ✅ Only used for CTM API and OpenAI API calls

### Data Privacy
- ✅ Scripts run **locally on your machine**
- ✅ No telemetry or tracking
- ✅ No automatic data uploads
- ✅ Output files saved only in your Documents folder

### Keychain Safety
When you first configure credentials, macOS may ask for your system password once. This is normal—it's securing your credentials in the encrypted Keychain. This happens once at setup.

---

## ❓ Troubleshooting

### "App Cannot Be Verified"
**Solution:** This is normal for unsigned apps
1. Try to launch the app
2. See the warning? Go to **System Settings** → **Security & Privacy**
3. Find "CTM Companion" and click **"Open Anyway"**
4. App now runs normally (no warning next time)

### "Python Not Found"
**Solution:** Install Python via Homebrew
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python3
```
Then restart the app.

### "CTM Credentials Error"
**Solution:** Verify your credentials
1. Go to Settings (Cmd+,)
2. Check for green checkmarks next to credentials
3. If missing: Copy fresh token from CTM Settings → API Keys
4. Verify Account ID is correct

### "No Notification Received"
**Solution:** Enable notifications
1. **System Settings** → **Notifications**
2. Find "CTM Companion"
3. Toggle notifications ON
4. Make sure "Allow Notifications" is enabled

### "Results Not Saving"
**Solution:** Check output folder
1. Go to Settings → Output tab
2. Verify folder path is accessible
3. Check free disk space (need ~100 MB)
4. Try a different folder in Documents

### Reports Take Too Long
**Solution:** Optimize your query
1. Use narrower date ranges
2. Run during off-peak hours
3. Check CTM API status
4. Reduce call limits in parameters

---

## 📊 Understanding Results

### HTML Reports
- **Best for:** Sharing, printing, quick reviews
- **Open with:** Any web browser
- **Download:** Right-click → Save to keep a copy
- **Share:** Send the HTML file or take a screenshot

### CSV Files
- **Best for:** Analysis, Excel/Sheets import, further processing
- **Open with:** Excel, Google Sheets, or any spreadsheet app
- **Format:** Standard comma-separated values
- **Use:** Pivot tables, charts, custom analysis

### View Output Files
After running a tool:
1. Results appear in the "Output Files" section
2. Click **"Open"** to view in browser/app
3. Click **"Reveal"** to show in Finder
4. Click file name to copy path

---

## 🚀 Best Practices

### Daily Workflow
1. **Morning**: Run Daily Summary to see yesterday's performance
2. **Mid-day**: Run Account Assessment One-Pager for quick check-in
3. **End of week**: Run full Account Assessment for detailed analysis
4. **As needed**: Use AskAI for prompt optimization

### Monthly Reviews
1. Run full Account Assessment
2. Export all CSVs to Excel
3. Create dashboards for trends
4. Compare month-over-month

### Troubleshooting Performance
1. Check Python tab for status
2. Review History tab for error messages
3. Try running a different tool to isolate issues
4. Restart the app if stuck

---

## 📈 Uninstall

To completely remove the app:

```bash
# Remove the app
rm -rf /Applications/CTMCompanion.app

# Remove user data (optional)
rm -rf ~/Library/Application\ Support/CTMCompanion

# Remove output files (optional)
rm -rf ~/Documents/CTM\ Companion
```

Credentials stored in Keychain are automatically removed when the app is deleted.

---

## 📞 Support

### Check Status
1. Go to Settings (Cmd+,)
2. Python tab shows environment status
3. History tab shows all recent runs and errors

### Common Questions

**Q: Can I use multiple CTM accounts?**
A: Yes! Change Account ID in tool parameters before running. Credentials stay the same if same server.

**Q: Do I need internet?**
A: Only for CTM API and OpenAI API calls. Python environment setup needs internet once.

**Q: How much data do you collect?**
A: None. The app is completely local. No tracking or telemetry.

**Q: Can I edit the scripts?**
A: The Python scripts are bundled in the app. Advanced users can extract and modify them at: `~/Library/Application Support/CTMCompanion/scripts/`

**Q: How often can I run tools?**
A: As often as you need. No limits or rate limiting from the app. CTM API rate limits may apply.

---

## 🔄 Updates

### Check for Updates
- Download the latest DMG from [Releases](https://github.com/CTMJSON/ctm-companion/releases)
- Drag new version to Applications (confirm overwrite)
- Settings and history are preserved

### Version History
- **v1.0** (May 2026): Initial release
  - All 6 tools integrated
  - Professional UI with CTM branding
  - Auto-open HTML results
  - Secure keychain storage
  - Run history and notifications

---

## 🎉 Get Started Now

1. [Download the latest release](https://github.com/CTMJSON/ctm-companion/releases)
2. Install to Applications (drag and drop)
3. Launch and configure credentials
4. Run your first report in seconds

**Questions?** Check Settings (Cmd+,) or review the Troubleshooting section above.

---

**CTM Companion v1.0**  
*Professional macOS App for CTM Users*  
Built with SwiftUI • Secure by Default • Ready to Use
