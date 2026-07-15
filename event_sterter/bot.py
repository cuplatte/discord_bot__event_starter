"""
Discord 企画管理Bot
--------------------
/企画開始 : 参加者ロール・閲覧者ロールを作成し、企画チャンネルを立てて
           リアクション参加用メッセージを投稿する（誰でも実行可）
/企画終了 : 確認ボタンを経て、チャンネルをアーカイブへ移動し、
           2つのロールを削除する（管理者ロールのみ）

環境変数:
  DISCORD_TOKEN       : Botトークン（必須）
  ARCHIVE_CATEGORY    : アーカイブ用カテゴリ名（省略時 "アーカイブ"）
  ACTIVE_CATEGORY     : 進行中企画用カテゴリ名（省略時 "進行中の企画"）
  ADMIN_ROLE_NAME     : /企画終了 を許可する管理者ロール名（省略時 "管理者"）
"""

import os
import datetime
import discord
from discord import app_commands
from discord.ext import commands

# ---- 設定 ----------------------------------------------------------------
TOKEN = os.environ["DISCORD_TOKEN"]
ARCHIVE_CATEGORY = os.environ.get("ARCHIVE_CATEGORY", "アーカイブ")
ACTIVE_CATEGORY = os.environ.get("ACTIVE_CATEGORY", "進行中の企画")
ADMIN_ROLE_NAME = os.environ.get("ADMIN_ROLE_NAME", "管理者")

# リアクション絵文字とロール種別の対応
EMOJI_PARTICIPANT = "✅"  # 参加者ロール
EMOJI_VIEWER = "👀"        # 閲覧者ロール

# ---- Intents / Bot -------------------------------------------------------
intents = discord.Intents.default()
intents.members = True          # ロール付与・メンバー取得に必要（Privileged）
intents.message_content = False # メッセージ本文は使わないのでOFF

bot = commands.Bot(command_prefix="!", intents=intents)


# ---- ユーティリティ ------------------------------------------------------
def project_prefix() -> str:
    """企画名に付ける年月プレフィックス（例: 2026-02_）"""
    return datetime.datetime.now().strftime("%Y-%m") + "_"


async def get_or_create_category(guild: discord.Guild, name: str,
                                  overwrites=None) -> discord.CategoryChannel:
    """指定名のカテゴリを取得。無ければ作成する。"""
    category = discord.utils.get(guild.categories, name=name)
    if category is None:
        category = await guild.create_category(name, overwrites=overwrites or {})
    return category


# ---- /企画開始 -----------------------------------------------------------
@bot.tree.command(name="企画開始", description="新しい企画のロールとチャンネルを作成します")
@app_commands.describe(企画名="企画のタイトル（年月は自動で付きます）")
async def project_start(interaction: discord.Interaction, 企画名: str):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    base_name = project_prefix() + 企画名

    # --- ロール作成 ---
    participant_role = await guild.create_role(
        name=f"{base_name}_参加者",
        mentionable=True,
        reason=f"企画開始: {base_name}",
    )
    viewer_role = await guild.create_role(
        name=f"{base_name}_閲覧者",
        mentionable=True,
        reason=f"企画開始: {base_name}",
    )

    # --- チャンネル権限（進行中）---
    # @everyone は見えない。2ロールは閲覧・送信とも可。
    # Bot自身も閲覧・送信・リアクション可にしておかないと、
    # 作成直後のメッセージ投稿が 403 Missing Access で失敗する。
    #
    # mention_everyone=False で、このチャンネルでは誰も @everyone / @here を
    # 使えないようにする。閲覧者に通知を飛ばさず、参加者へは参加者ロールの
    # メンションで連絡してもらう運用にするため。
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False, mention_everyone=False,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, add_reactions=True,
            manage_messages=True, read_message_history=True,
        ),
        participant_role: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, mention_everyone=False,
        ),
        viewer_role: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, mention_everyone=False,
        ),
    }

    active_category = await get_or_create_category(guild, ACTIVE_CATEGORY)
    channel = await guild.create_text_channel(
        name=base_name,
        category=active_category,
        overwrites=overwrites,
        reason=f"企画開始: {base_name}",
    )

    # --- リアクション参加メッセージ ---
    # 参加案内は「コマンドを実行したチャンネル」に投稿する。
    # 企画チャンネルは初期状態で @everyone 非表示のため、そこに案内を出すと
    # まだ参加していない人が案内を見られない。全員が見える実行チャンネルに出す。
    embed = discord.Embed(
        title=f"📢 {企画名}",
        description=(
            f"新しい企画が始まりました！参加する人はリアクションを押してください。\n\n"
            f"{EMOJI_PARTICIPANT} 参加者として参加\n"
            f"{EMOJI_VIEWER} 閲覧者として参加\n\n"
            f"リアクションを押すと企画チャンネルが見えるようになります。\n"
            f"リアクションを外すとロールも外れます。"
        ),
        color=0x5865F2,
    )
    # ロールIDをフッターに埋め込み、リアクション処理時に参照する
    embed.set_footer(text=f"pids:{participant_role.id}:{viewer_role.id}")

    # コマンドを実行したチャンネルに投稿（Bot・全員が見えるので権限エラーにならない）
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction(EMOJI_PARTICIPANT)
    await msg.add_reaction(EMOJI_VIEWER)

    # --- 企画チャンネル内に、通知運用の案内を投稿 ---
    # このチャンネルでは @everyone が使えないので、参加者全員に連絡したいときは
    # 参加者ロールをメンションするよう案内する。閲覧者には通知が飛ばない。
    guide = discord.Embed(
        title="📌 このチャンネルでの連絡方法",
        description=(
            f"このチャンネルでは `@everyone` / `@here` は使えません。\n\n"
            f"**参加者全員に通知したいとき**は、下記の参加者ロールをメンションしてください。\n"
            f"閲覧者には通知が飛びません。\n\n"
            f"🔔 参加者へ通知: {participant_role.mention}"
        ),
        color=0x57F287,
    )
    # ロールメンションを実際に通知として飛ばさないよう、案内では抑制する
    await channel.send(
        embed=guide,
        allowed_mentions=discord.AllowedMentions.none(),
    )

    await interaction.followup.send(
        f"企画「{base_name}」を作成しました → {channel.mention}\n"
        f"参加募集メッセージをこのチャンネルに投稿しました。", ephemeral=True
    )


# ---- リアクションによるロール付与/剥奪 -----------------------------------
def _extract_role_ids(embed: discord.Embed):
    """埋め込みフッターから (participant_id, viewer_id) を取り出す。"""
    if not embed.footer or not embed.footer.text:
        return None
    text = embed.footer.text
    if not text.startswith("pids:"):
        return None
    try:
        _, pid, vid = text.split(":")
        return int(pid), int(vid)
    except ValueError:
        return None


async def _handle_reaction(payload: discord.RawReactionActionEvent, add: bool):
    if payload.guild_id is None:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    channel = guild.get_channel(payload.channel_id)
    if channel is None:
        return

    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return
    if not message.embeds:
        return

    ids = _extract_role_ids(message.embeds[0])
    if ids is None:
        return
    participant_id, viewer_id = ids

    emoji = str(payload.emoji)
    if emoji == EMOJI_PARTICIPANT:
        role = guild.get_role(participant_id)
    elif emoji == EMOJI_VIEWER:
        role = guild.get_role(viewer_id)
    else:
        return

    if role is None:
        return

    try:
        if add:
            await member.add_roles(role, reason="リアクション参加")
        else:
            await member.remove_roles(role, reason="リアクション離脱")
    except discord.Forbidden:
        pass  # Botのロール順位が対象ロールより下だと失敗する


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    await _handle_reaction(payload, add=True)


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    await _handle_reaction(payload, add=False)


# ---- /企画終了 -----------------------------------------------------------
class ConfirmEndView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, invoker_id: int):
        super().__init__(timeout=60)
        self.channel = channel
        self.invoker_id = invoker_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # コマンド実行者本人のみボタン操作可
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "この操作はコマンド実行者のみ可能です。", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="企画を終了する", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        channel = self.channel
        base_name = channel.name

        # アーカイブカテゴリ（@everyone 閲覧可・送信不可）を用意
        archive_overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True, send_messages=False
            )
        }
        archive_category = await get_or_create_category(
            guild, ARCHIVE_CATEGORY, overwrites=archive_overwrites
        )

        # チャンネルをアーカイブへ移動し、カテゴリ権限に同期
        await channel.edit(
            category=archive_category,
            sync_permissions=True,
            reason=f"企画終了アーカイブ: {base_name}",
        )

        # 対応する2ロールを削除
        deleted = []
        for suffix in ("_参加者", "_閲覧者"):
            role = discord.utils.get(guild.roles, name=base_name + suffix)
            if role is not None:
                await role.delete(reason=f"企画終了: {base_name}")
                deleted.append(role.name)

        await channel.send("🔒 この企画は終了しました。チャンネルは閲覧のみ可能です。")
        await interaction.followup.send(
            f"「{base_name}」を終了しました。\n"
            f"・アーカイブへ移動\n"
            f"・削除ロール: {', '.join(deleted) if deleted else 'なし'}",
            ephemeral=True,
        )
        self.stop()

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("キャンセルしました。", ephemeral=True)
        self.stop()


def has_admin_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(r.name == ADMIN_ROLE_NAME for r in interaction.user.roles)


@bot.tree.command(name="企画終了", description="企画をアーカイブし、ロールを削除します（管理者のみ）")
@app_commands.describe(channel="終了する企画チャンネル（省略時は実行チャンネル）")
async def project_end(interaction: discord.Interaction,
                      channel: discord.TextChannel = None):
    if not has_admin_role(interaction):
        await interaction.response.send_message(
            f"このコマンドは「{ADMIN_ROLE_NAME}」ロールを持つ人のみ実行できます。",
            ephemeral=True,
        )
        return

    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        await interaction.response.send_message(
            "テキストチャンネルを指定してください。", ephemeral=True
        )
        return

    view = ConfirmEndView(target, interaction.user.id)
    await interaction.response.send_message(
        f"⚠️ **{target.name}** を終了します。\n"
        f"・チャンネルを「{ARCHIVE_CATEGORY}」へ移動（全員閲覧可・書き込み不可）\n"
        f"・参加者ロール／閲覧者ロールを削除\n\n"
        f"よろしいですか？",
        view=view,
        ephemeral=True,
    )


# ---- 起動 ----------------------------------------------------------------
@bot.event
async def on_ready():
    try:
        guild_id = os.environ.get("GUILD_ID")
        if guild_id:
            # ギルド（サーバー）限定同期。反映が即時なのでテスト時に便利。
            # 注意: copy_global_to は使わない。使うと過去にグローバル登録された
            # 他Botのコマンドまで取り込んでしまい、コマンドが混線する。
            # このBot自身が定義したコマンドだけをギルドへ同期する。
            guild = discord.Object(id=int(guild_id))
            synced = await bot.tree.sync(guild=guild)
            print(f"Slash commands synced to guild {guild_id}: {len(synced)}")
        else:
            # グローバル同期（全サーバーに反映されるが最大1時間かかる）
            synced = await bot.tree.sync()
            print(f"Slash commands synced (global): {len(synced)}")
    except Exception as e:
        print(f"Sync failed: {e}")
    print(f"Logged in as {bot.user}")


if __name__ == "__main__":
    bot.run(TOKEN)