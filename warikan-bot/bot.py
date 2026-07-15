"""
Discord 割り勘Bot（walica連携）
--------------------------------
/割り勘 : コマンドを実行した企画チャンネルの「参加者ロール」保持者を集め、
         チャンネル名をタイトルとして walica.jp に割り勘を作成し、
         作成されたURLをチャンネルに投稿する。

前提:
  - 企画チャンネル名は "2026-07_企画名" 形式
  - 参加者ロール名は "{チャンネル名}_参加者"（企画BotのcreateルールとⅠ致）
  - メンバー名は Discord の表示名（ニックネーム）を使用

環境変数:
  DISCORD_TOKEN        : Botトークン（必須）
  WALICA_HEADLESS      : "1" でヘッドレス（省略時 "1"）

依存:
  discord.py>=2.4.0
  playwright>=1.40      （+ playwright install chromium）
"""

import os
import discord
from discord import app_commands
from discord.ext import commands

from walica import create_walica_project  # walica操作は別モジュールに分離

# ---- 設定 ----------------------------------------------------------------
TOKEN = os.environ["DISCORD_TOKEN"]
PARTICIPANT_SUFFIX = "_参加者"  # 企画Botが作るロールの接尾辞

# ---- Intents / Bot -------------------------------------------------------
intents = discord.Intents.default()
intents.members = True  # ロール保持者の取得に必要（Privileged）

bot = commands.Bot(command_prefix="!", intents=intents)


def find_participant_role(channel: discord.TextChannel) -> discord.Role | None:
    """チャンネル名から対応する参加者ロールを探す。"""
    guild = channel.guild
    role_name = channel.name + PARTICIPANT_SUFFIX
    return discord.utils.get(guild.roles, name=role_name)


def collect_member_names(role: discord.Role) -> list[str]:
    """ロール保持者の表示名（ニックネーム）を集める。Botは除外。"""
    names = []
    for member in role.members:
        if member.bot:
            continue
        names.append(member.display_name)
    return names


# ---- /割り勘 -------------------------------------------------------------
@bot.tree.command(name="割り勘", description="このチャンネルの参加者でwalica割り勘を作成します")
async def warikan(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "テキストチャンネル内で実行してください。", ephemeral=True
        )
        return

    # --- 参加者ロールを特定 ---
    role = find_participant_role(channel)
    if role is None:
        await interaction.response.send_message(
            f"このチャンネルに対応する参加者ロール "
            f"（`{channel.name}{PARTICIPANT_SUFFIX}`）が見つかりません。\n"
            f"企画チャンネル内で実行してください。",
            ephemeral=True,
        )
        return

    # --- メンバー名を収集 ---
    names = collect_member_names(role)
    if not names:
        await interaction.response.send_message(
            "参加者ロールを持つメンバーがいません。", ephemeral=True
        )
        return

    title = channel.name  # チャンネル名をそのままタイトルに

    # walica操作は時間がかかるので応答を保留
    await interaction.response.defer()

    # --- walica で割り勘作成 ---
    try:
        url = await create_walica_project(title, names)
    except Exception as e:
        await interaction.followup.send(
            f"割り勘の作成中にエラーが発生しました:\n```{e}```", ephemeral=True
        )
        return

    # --- 結果を投稿 ---
    member_list = "、".join(names)
    embed = discord.Embed(
        title="💰 割り勘を作成しました",
        description=(
            f"**{title}**\n\n"
            f"参加者（{len(names)}人）: {member_list}\n\n"
            f"🔗 {url}"
        ),
        color=0xFEE75C,
    )
    await interaction.followup.send(embed=embed)


# ---- 起動 ----------------------------------------------------------------
@bot.event
async def on_ready():
    try:
        guild_id = os.environ.get("GUILD_ID")
        if guild_id:
            # ギルド（サーバー）限定同期。反映が即時で、他Botと干渉しない。
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Slash commands synced to guild {guild_id}: {len(synced)}")
        else:
            synced = await bot.tree.sync()
            print(f"Slash commands synced (global): {len(synced)}")
    except Exception as e:
        print(f"Sync failed: {e}")
    print(f"Logged in as {bot.user}")


if __name__ == "__main__":
    bot.run(TOKEN)