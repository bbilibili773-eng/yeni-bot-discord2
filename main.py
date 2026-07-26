import discord
from discord.ext import commands
import json
import asyncio
import datetime
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as env_file:
        for line in env_file:
            if line.startswith("DISCORD_TOKEN="):
                os.environ["DISCORD_TOKEN"] = line.strip().split("=", 1)[1]

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

TOKEN  = os.getenv("DISCORD_TOKEN") or config.get("token")
PREFIX = config.get("prefix", "!")

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

ticket_spam    = {}
acik_ticketlar = {}


# ── İZİNLER ──────────────────────────────────────────────────────────────────

def get_perms(name):
    if name == "administrator": return discord.Permissions(administrator=True)
    if name == "manage_guild":  return discord.Permissions(manage_guild=True)
    if name == "moderator":
        return discord.Permissions(
            kick_members=True, ban_members=True, manage_messages=True,
            mute_members=True, deafen_members=True, move_members=True,
            manage_nicknames=True, moderate_members=True
        )
    return discord.Permissions.none()


# ── KURULUM ───────────────────────────────────────────────────────────────────

async def temizle(guild):
    for ch in list(guild.channels):
        try: await ch.delete(); await asyncio.sleep(0.3)
        except: pass
    for r in list(guild.roles):
        if r.name != "@everyone" and not r.managed and r < guild.me.top_role:
            try: await r.delete(); await asyncio.sleep(0.3)
            except: pass


async def kur(guild):
    tmpl     = config["server_template"]
    roles_map = {}
    everyone  = guild.default_role
    await everyone.edit(permissions=discord.Permissions.none())
    await asyncio.sleep(0.3)

    for rd in reversed(tmpl["roles"]):
        r = await guild.create_role(
            name=rd["name"],
            color=discord.Color(int(rd.get("color","0x99AAB5"), 16)),
            hoist=rd.get("hoist", False),
            mentionable=rd.get("mentionable", False),
            permissions=get_perms(rd.get("permissions","none"))
        )
        roles_map[rd["name"]] = r
        await asyncio.sleep(0.5)

    uye_r    = next((r for n,r in roles_map.items() if "Üye"   in n), None)
    abone_r  = next((r for n,r in roles_map.items() if "Abone" in n), None)
    kurucu_r = next((r for n,r in roles_map.items() if "Kurucu" in n), None)
    staff_rs  = [r for n,r in roles_map.items() if any(
        k in n for k in ["Kurucu","Yönetici","Moderatör","Deneme","Destek"]
    )]

    for cat in tmpl["categories"]:
        cat_ow = {everyone: discord.PermissionOverwrite(view_channel=False)}
        if "YÖNETİM" in cat["name"].upper():
            for sr in staff_rs:
                cat_ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        else:
            if uye_r:   cat_ow[uye_r]   = discord.PermissionOverwrite(view_channel=True)
            if abone_r: cat_ow[abone_r] = discord.PermissionOverwrite(view_channel=True)

        category = await guild.create_category(cat["name"], overwrites=cat_ow)
        await asyncio.sleep(0.5)

        for ch in cat.get("channels", []):
            if ch.get("type") == "voice":
                await guild.create_voice_channel(ch["name"], category=category)
                await asyncio.sleep(0.5)
                continue

            ow = dict(cat_ow)

            if "abone-ss" in ch["name"]:
                ow[everyone] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    attach_files=True, read_message_history=True
                )
            elif "ticket" in ch["name"]:
                ow[everyone] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=False, read_message_history=True
                )
                if uye_r:   ow[uye_r]   = discord.PermissionOverwrite(view_channel=True, send_messages=False)
                if abone_r: ow[abone_r] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
            elif ch.get("staff_only"):
                ow[everyone] = discord.PermissionOverwrite(view_channel=False)
                if uye_r:   ow[uye_r]   = discord.PermissionOverwrite(view_channel=False)
                if abone_r: ow[abone_r] = discord.PermissionOverwrite(view_channel=False)
                for sr in staff_rs:
                    ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            elif ch.get("kurucu_only"):
                # Sadece kurucu yazar, üyeler okuyabilir
                if uye_r:    ow[uye_r]    = discord.PermissionOverwrite(view_channel=True, send_messages=False)
                if abone_r:  ow[abone_r]  = discord.PermissionOverwrite(view_channel=True, send_messages=False)
                if kurucu_r: ow[kurucu_r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                for sr in staff_rs:
                    ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
                if kurucu_r: ow[kurucu_r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            elif ch.get("readonly"):
                if uye_r:   ow[uye_r]   = discord.PermissionOverwrite(view_channel=True, send_messages=False)
                if abone_r: ow[abone_r] = discord.PermissionOverwrite(view_channel=True, send_messages=False)

            await guild.create_text_channel(
                ch["name"], category=category,
                topic=ch.get("topic",""), overwrites=ow
            )
            await asyncio.sleep(0.5)

    return len(roles_map)


# ── TICKET ────────────────────────────────────────────────────────────────────

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ticket Aç", style=discord.ButtonStyle.green, custom_id="ticket_ac")
    async def ac(self, interaction: discord.Interaction, button: discord.ui.Button):
        user  = interaction.user
        guild = interaction.guild
        now   = datetime.datetime.now()

        spam = [t for t in ticket_spam.get(user.id, []) if (now - t).seconds < 300]
        ticket_spam[user.id] = spam
        if len(spam) >= 2:
            await interaction.response.send_message("❌ 5 dakikada en fazla 2 ticket açabilirsin!", ephemeral=True)
            return

        if user.id in acik_ticketlar:
            ch = guild.get_channel(acik_ticketlar[user.id])
            if ch:
                await interaction.response.send_message(f"❌ Zaten açık ticketin var: {ch.mention}", ephemeral=True)
                return

        ticket_spam[user.id].append(now)

        cat = discord.utils.get(guild.categories, name="🎫 ┃ TİCKETLAR")
        if not cat:
            cat = await guild.create_category("🎫 ┃ TİCKETLAR")

        mod_r = discord.utils.get(guild.roles, name="🛡️ Moderatör")
        yon_r = discord.utils.get(guild.roles, name="⚙️ Yönetici")
        kur_r = discord.utils.get(guild.roles, name="👑 Kurucu")

        ow = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)
        }
        for sr in [mod_r, yon_r, kur_r]:
            if sr: ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ch = await guild.create_text_channel(
            f"ticket-{user.name}", category=cat, overwrites=ow,
            topic=f"{user} tarafından açıldı."
        )
        acik_ticketlar[user.id] = ch.id

        embed = discord.Embed(
            title="🎫 Destek Talebi",
            description=f"Merhaba {user.mention}!\n\nSorununuzu yazın, yetkili ekip yanıt verecek.\n\nKapatmak için butona basın.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Ticket ID: {ch.id}")
        await ch.send(embed=embed, view=TicketKapatView())
        await interaction.response.send_message(f"✅ Ticketin açıldı: {ch.mention}", ephemeral=True)


class TicketKapatView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Kapat", style=discord.ButtonStyle.red, custom_id="ticket_kapat")
    async def kapat(self, interaction: discord.Interaction, button: discord.ui.Button):
        ch = interaction.channel
        for uid, cid in list(acik_ticketlar.items()):
            if cid == ch.id:
                del acik_ticketlar[uid]; break
        embed = discord.Embed(
            title="🔒 Kapatılıyor",
            description=f"{interaction.user.mention} kapattı. 5 saniye sonra silinecek.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        await ch.delete()


# ── ABONE SS ONAY ─────────────────────────────────────────────────────────────

class AboneOnayView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.green)
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild  = interaction.guild
        member = guild.get_member(self.user_id)
        if not member:
            await interaction.response.send_message("❌ Üye bulunamadı.", ephemeral=True); return

        abone_r = discord.utils.get(guild.roles, name="🎯 Abone")
        if not abone_r:
            abone_r = await guild.create_role(name="🎯 Abone", color=discord.Color.orange(), hoist=True)
        await member.add_roles(abone_r)

        embed = discord.Embed(
            title="✅ Onaylandı",
            description=f"{member.mention} → **Abone** rolü verildi.\nOnaylayan: {interaction.user.mention}",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)
        try:
            await member.send(embed=discord.Embed(
                title="🎉 Abone Rolü Verildi!",
                description=f"**{guild.name}** sunucusunda abone rolün onaylandı!",
                color=discord.Color.green()
            ))
        except: pass

    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.red)
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild  = interaction.guild
        member = guild.get_member(self.user_id)
        embed  = discord.Embed(
            title="❌ Reddedildi",
            description=f"{member.mention if member else 'Üye'} reddedildi.\nReddeden: {interaction.user.mention}",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)
        if member:
            try:
                await member.send(embed=discord.Embed(
                    title="❌ SS Reddedildi",
                    description=f"**{guild.name}** sunucusunda SS'in reddedildi. Geçerli bir SS at.",
                    color=discord.Color.red()
                ))
            except: pass


# ── EVENTLER ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot hazir: {bot.user} ({bot.user.id})")
    bot.add_view(TicketView())
    bot.add_view(TicketKapatView())
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}yardim"))


def welcome_channel(guild):
    """hoş-geldin, welcome veya giriş-çıkış kanalını bulur."""
    if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
        return guild.system_channel

    target_names = [
        "📌・hoş-geldin", "hoş-geldin", "📌・welcome", "welcome",
        "giriş-çıkış", "📌・giriş-çıkış", "giris-cikis", "giriş",
        "📌・giriş", "giriş-çıkış-bildirimleri", "giriş-çıkış-mesajları"
    ]
    for name in target_names:
        ch = discord.utils.get(guild.text_channels, name=name)
        if ch and ch.permissions_for(guild.me).send_messages:
            return ch

    for ch in guild.text_channels:
        name_lower = ch.name.lower()
        if any(k in name_lower for k in ["geldin", "welcome", "giris", "giriş", "cikis", "çıkış"]):
            if ch.permissions_for(guild.me).send_messages:
                return ch

    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).send_messages:
            return ch
    return None


@bot.event
async def on_member_join(member):
    guild = member.guild
    kayitsiz = discord.utils.get(guild.roles, name="🆕 Kayıtsız")
    if kayitsiz:
        try: await member.add_roles(kayitsiz)
        except: pass

    ch = welcome_channel(guild)
    if ch:
        embed = discord.Embed(
            title="🎉 Yeni Üye Katıldı!",
            description=(
                f"Hoş geldin {member.mention}!\n\n"
                f"🎫 Sorun için **tickets** kanalından ticket aç."
            ),
            color=discord.Color.green()
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Üye", value=member.mention, inline=True)
        embed.add_field(name="📅 Hesap", value=member.created_at.strftime("%d.%m.%Y"), inline=True)
        embed.set_footer(
            text=f"Seninle birlikte {guild.member_count} kişi olduk! 🎊",
            icon_url=guild.icon.url if guild.icon else None
        )
        await ch.send(embed=embed)


@bot.event
async def on_member_remove(member):
    guild = member.guild
    ch = welcome_channel(guild)
    if ch:
        embed = discord.Embed(
            title="👋 Üye Ayrıldı",
            description=f"**{member.display_name}** sunucudan ayrıldı.",
            color=discord.Color.red()
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Üye", value=str(member), inline=True)
        embed.add_field(name="🆔 ID", value=str(member.id), inline=True)
        embed.set_footer(
            text=f"Şu an {guild.member_count} kişiyiz.",
            icon_url=guild.icon.url if guild.icon else None
        )
        await ch.send(embed=embed)


@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message); return

    # ── LINK / DAVET KORUMASI ──
    # Yönetici ve moderatörler hariç herkesten link sil
    LINK_PATTERNS = ["discord.gg/", "discord.com/invite/", "http://", "https://"]
    if any(p in message.content.lower() for p in LINK_PATTERNS):
        # Yetkili rolleri kontrol et
        yetkili_roller = ["👑 Kurucu", "⚙️ Yönetici", "🛡️ Moderatör"]
        kullanici_rolleri = [r.name for r in message.author.roles]
        if not any(r in kullanici_rolleri for r in yetkili_roller):
            try: await message.delete()
            except: pass
            try:
                uyari = await message.channel.send(
                    f"⛔ {message.author.mention} link atmak yasaktır!",
                )
                await asyncio.sleep(5)
                await uyari.delete()
            except: pass
            return

    # ── ABONE-SS KANALI ──
    if "abone-ss" in message.channel.name:
        has_img = any(
            a.content_type and a.content_type.startswith("image/")
            for a in message.attachments
        )
        if not has_img:
            try: await message.delete()
            except: pass
            try:
                await message.author.send(embed=discord.Embed(
                    title="❌ Sadece Resim!",
                    description="**abone-ss** kanalına sadece ekran görüntüsü atabilirsin. Link ve metin yasaktır.",
                    color=discord.Color.red()
                ))
            except: pass
            return

        guild   = message.guild
        onay_ch = (discord.utils.get(guild.text_channels, name="📋・mod-log") or
                   discord.utils.get(guild.text_channels, name="💼・yetkili-sohbet"))
        if onay_ch:
            embed = discord.Embed(
                title="📸 Abone SS Onayı",
                description=f"**Üye:** {message.author.mention}\n**Kanal:** {message.channel.mention}\n\nOnayla veya reddet.",
                color=discord.Color.orange()
            )
            embed.set_image(url=message.attachments[0].url)
            embed.set_footer(text=f"User ID: {message.author.id}")
            await onay_ch.send(embed=embed, view=AboneOnayView(message.author.id))
        await message.reply("✅ SS'in alındı! Yetkili onayından sonra **Abone** rolü verilecek.", delete_after=10)

    await bot.process_commands(message)


# ── MOD KOMUTLARI ─────────────────────────────────────────────────────────────

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, sebep="Sebep belirtilmedi."):
    await member.ban(reason=sebep)
    embed = discord.Embed(title="🔨 Yasaklandı", description=f"{member.mention} yasaklandı.\n**Sebep:** {sebep}", color=discord.Color.red())
    embed.set_footer(text=f"Yetkili: {ctx.author}")
    await ctx.send(embed=embed)
    try: await member.send(embed=discord.Embed(title="🔨 Yasaklandın", description=f"**{ctx.guild.name}** sunucusundan yasaklandın.\n**Sebep:** {sebep}", color=discord.Color.red()))
    except: pass


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, sebep="Sebep belirtilmedi."):
    await member.kick(reason=sebep)
    embed = discord.Embed(title="👢 Atıldı", description=f"{member.mention} atıldı.\n**Sebep:** {sebep}", color=discord.Color.orange())
    embed.set_footer(text=f"Yetkili: {ctx.author}")
    await ctx.send(embed=embed)
    try: await member.send(embed=discord.Embed(title="👢 Atıldın", description=f"**{ctx.guild.name}** sunucusundan atıldın.\n**Sebep:** {sebep}", color=discord.Color.orange()))
    except: pass


@bot.command(name="sus", aliases=["mute"])
@commands.has_permissions(moderate_members=True)
async def sus(ctx, member: discord.Member, dakika: int = 10, *, sebep="Sebep belirtilmedi."):
    sure = datetime.timedelta(minutes=dakika)
    await member.timeout(sure, reason=sebep)
    embed = discord.Embed(title="🔇 Susturuldu", description=f"{member.mention} **{dakika} dakika** susturuldu.\n**Sebep:** {sebep}", color=discord.Color.orange())
    embed.set_footer(text=f"Yetkili: {ctx.author}")
    await ctx.send(embed=embed)
    try: await member.send(embed=discord.Embed(title="🔇 Susturuldun", description=f"**{ctx.guild.name}** sunucusunda {dakika} dakika susturuldun.\n**Sebep:** {sebep}", color=discord.Color.orange()))
    except: pass


@bot.command(name="sussuz", aliases=["unmute"])
@commands.has_permissions(moderate_members=True)
async def sussuz(ctx, member: discord.Member):
    await member.timeout(None)
    embed = discord.Embed(title="🔊 Susturma Kaldırıldı", description=f"{member.mention} artık konuşabilir.", color=discord.Color.green())
    embed.set_footer(text=f"Yetkili: {ctx.author}")
    await ctx.send(embed=embed)


@bot.command(name="temizle", aliases=["clear", "purge"])
@commands.has_permissions(manage_messages=True)
async def temizle_cmd(ctx, adet: int = 10):
    await ctx.channel.purge(limit=adet + 1)
    msg = await ctx.send(embed=discord.Embed(description=f"🗑️ {adet} mesaj silindi.", color=discord.Color.green()))
    await asyncio.sleep(3)
    try: await msg.delete()
    except: pass


@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(embed=discord.Embed(title="✅ Yasak Kaldırıldı", description=f"**{user}** yasağı kaldırıldı.", color=discord.Color.green()))


# ── GENEL KOMUTLAR ────────────────────────────────────────────────────────────

@bot.command(name="kayit")
@commands.has_permissions(manage_roles=True)
async def kayit(ctx, member: discord.Member):
    guild    = ctx.guild
    kayitsiz = discord.utils.get(guild.roles, name="🆕 Kayıtsız")
    uye      = discord.utils.get(guild.roles, name="✅ Üye")
    if not uye:
        await ctx.send("❌ `✅ Üye` rolü bulunamadı. Önce `!kurulum` çalıştır."); return
    if kayitsiz and kayitsiz in member.roles:
        await member.remove_roles(kayitsiz)
    await member.add_roles(uye)
    embed = discord.Embed(title="✅ Kayıt Başarılı!", description=f"{member.mention} kayıt edildi!", color=discord.Color.green())
    embed.set_footer(text=f"Kaydeden: {ctx.author}")
    await ctx.send(embed=embed)
    try:
        await member.send(embed=discord.Embed(
            title=f"👋 {guild.name} Sunucusuna Hoş Geldin!",
            description="Kayıt tamamlandı, artık tüm kanalları görebilirsin!",
            color=discord.Color.blurple()
        ))
    except: pass


@bot.command(name="kurulum", aliases=["kur", "setup"])
@commands.has_permissions(administrator=True)
async def kurulum(ctx, mod=""):
    reset = mod.lower() in ("sifirla", "reset", "temizle")
    if reset:
        await ctx.send(embed=discord.Embed(
            title="⚠️ DIKKAT!",
            description="Tüm kanallar ve roller silinecek.\nDevam için `evet` yaz. (30 sn)",
            color=discord.Color.red()
        ))
        def check(m): return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏰ Süre doldu."); return
        if msg.content.lower() not in ("evet", "e", "yes", "y"):
            await ctx.send("❌ İptal."); return

    try: dm = await ctx.author.send("⚙️ Kurulum başlıyor...")
    except: dm = None

    try:
        if reset:
            if dm: await dm.edit(content="🗑️ Temizleniyor...")
            await temizle(ctx.guild)
        if dm: await dm.edit(content="🔨 Oluşturuluyor...")
        rol_sayisi = await kur(ctx.guild)

        ticket_ch = discord.utils.get(ctx.guild.text_channels, name="🎫・tickets")
        if ticket_ch:
            embed = discord.Embed(
                title="🎫 Destek Talebi Aç",
                description="Sorunuz için butona basın.\n\n⚠️ Gereksiz ticket açmayın.",
                color=discord.Color.blurple()
            )
            await ticket_ch.send(embed=embed, view=TicketView())

        hedef = next((c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).send_messages), None)
        bitis = discord.Embed(
            title="✅ Kurulum Tamamlandı!",
            description=(
                f"**{rol_sayisi} rol** ve tüm kanallar oluşturuldu.\n\n"
                "📌 Yeni üyeler sadece `abone-ss` görür.\n"
                "📸 SS atınca mod-log'a onay gider.\n"
                "🎫 Ticket sistemi aktif.\n"
                "✅ Kayıt: `!kayit @üye`\n"
                "🔨 Mod: `!ban` `!kick` `!sus` `!temizle`"
            ),
            color=discord.Color.green()
        )
        bitis.set_footer(text=f"Kuran: {ctx.author}")
        if hedef: await hedef.send(embed=bitis)
        if dm: await dm.edit(content="", embed=bitis)

    except discord.Forbidden:
        if dm: await dm.edit(content="❌ Yetki hatası! Bota Yönetici yetkisi ver.")
    except Exception as e:
        if dm: await dm.edit(content=f"❌ Hata: {e}")


@bot.command(name="ticketkur")
@commands.has_permissions(administrator=True)
async def ticketkur(ctx):
    embed = discord.Embed(title="🎫 Destek Talebi Aç", description="Sorunuz için butona basın.\n\n⚠️ Spam yapmayın.", color=discord.Color.blurple())
    await ctx.send(embed=embed, view=TicketView())
    try: await ctx.message.delete()
    except: pass


@bot.command(name="yardim")
async def yardim(ctx):
    embed = discord.Embed(title="📋 Komutlar", color=discord.Color.blurple())
    embed.add_field(name="⚙️ Kurulum", value=f"`{PREFIX}kurulum sifirla`", inline=False)
    embed.add_field(name="✅ Kayıt", value=f"`{PREFIX}kayit @üye`", inline=False)
    embed.add_field(name="🔨 Moderasyon", value=(
        f"`{PREFIX}ban @üye sebep`\n"
        f"`{PREFIX}kick @üye sebep`\n"
        f"`{PREFIX}sus @üye dakika sebep`\n"
        f"`{PREFIX}sussuz @üye`\n"
        f"`{PREFIX}temizle 10`\n"
        f"`{PREFIX}unban ID`"
    ), inline=False)
    embed.add_field(name="🎫 Ticket", value=f"`{PREFIX}ticketkur`", inline=False)
    embed.add_field(name="📊 Bilgi", value=f"`{PREFIX}sunucu`", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="sunucu", aliases=["si"])
async def sunucu(ctx):
    g = ctx.guild
    embed = discord.Embed(title=g.name, color=discord.Color.blurple())
    embed.add_field(name="👑 Sahip", value=str(g.owner), inline=True)
    embed.add_field(name="👥 Üyeler", value=g.member_count, inline=True)
    embed.add_field(name="📁 Kanallar", value=len(g.channels), inline=True)
    embed.add_field(name="🎭 Roller", value=len(g.roles), inline=True)
    if g.icon: embed.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=embed)


# ── HATA YÖNETİMİ ─────────────────────────────────────────────────────────────

@ban.error
@kick.error
@sus.error
@temizle_cmd.error
async def mod_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu komutu kullanmak için yetkin yok.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Üye bulunamadı.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Eksik parametre. `{PREFIX}yardim` yaz.")

@kurulum.error
async def kurulum_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Yönetici yetkisi gerekli.")

@kayit.error
async def kayit_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Kullanım: `{PREFIX}kayit @üye`")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Üye bulunamadı.")


try:
    from keep_alive import keep_alive
    keep_alive()
except Exception as e:
    print(f"Keep-alive başlatılamadı: {e}")

bot.run(TOKEN)
