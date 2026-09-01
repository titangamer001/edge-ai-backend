import os
import subprocess
import asyncio
import time
import discord

# We will rely entirely on environment variables (from Render or .env)
# Do NOT hardcode the token here!

# Initialize Discord Bot
intents = discord.Intents.default()
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"[DISCORD] Bot connected as {bot.user}")

async def start_discord_bot():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if token:
        try:
            await bot.start(token)
        except Exception as e:
            print(f"[DISCORD] Failed to start bot: {e}")

async def send_discord_alert(device_id, severity, message):
    await bot.wait_until_ready()
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    if not channel_id: return
        
    channel = bot.get_channel(int(channel_id))
    if not channel:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except:
            pass

    if channel:
        if severity == "stable":
            embed_color = 0x00FF00 # Green
            content_msg = "✅ **SYSTEM RESTORED & STABLE**"
            diff_block = f"```yaml\n+ {message}\n+ Network traffic has returned to normal baselines.```"
        else:
            embed_color = 0xFF0000 # Red
            content_msg = "🚨 **CRITICAL NETWORK INCIDENT DETECTED**"
            diff_block = f"```diff\n- {message}\n- Immediate intervention recommended.```"

        embed = discord.Embed(
            title=f"Infrastructure Update: {device_id}",
            description="Edge AI Telemetry Report.",
            color=embed_color
        )
        embed.add_field(name="Target Device", value=f"`{device_id}`", inline=True)
        embed.add_field(name="Current Status", value=f"`{severity.upper()}`", inline=True)
        embed.add_field(name="Diagnostic Details", value=diff_block, inline=False)
        embed.set_footer(text="Edge AI NOC")
        
        await channel.send(content=content_msg, embed=embed)
    else:
        print(f"[DISCORD] Could not find channel {channel_id}")


# Cooldown logic
ALERT_COOLDOWN = 15
_last_alert_time = 0

def trigger_external_alert(device_id, severity, message, loop=None):
    global _last_alert_time
    now = time.time()
    
    # Global cooldown to avoid Discord API Spam
    if severity != "stable":
        if now - _last_alert_time < ALERT_COOLDOWN:
            return
        _last_alert_time = now
    
    # Windows Native Toast removed - caused thread blocking issues
    # 2. Discord Bot Notification
    if loop:
        asyncio.run_coroutine_threadsafe(send_discord_alert(device_id, severity, message), loop)
