import discord
import requests
import os
import wget
import re
import asyncio
from datetime import datetime
from random import choice
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from __main__ import send_cmd_help
from __main__ import settings
from .utils import checks

TOKEN_URL = "https://graph.facebook.com/oauth/access_token?client_id={0}&client_secret={1}&grant_type=client_credentials"
#TODO this should be settable
FB_GROUP_URL = "https://graph.facebook.com/v3.2/276445842390059?fields=cover&access_token={0}"
FB_BANNER_URL = "https://graph.facebook.com/v3.2/{0}?fields=images&access_token={1}"

class Digest:
    """Handles posting a daily digest to specific channel(s)"""

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json('data/digest/settings.json')
        self.active_channels = dataIO.load_json('data/digest/active_channels.json')
        self.digests  = dataIO.load_json('data/digest/digests.json')
        # Example format:
        #self.digests = {
        #  {
        #    "user message life" : "user_id",
        #    "message" : "message_text",
        #    "life" : int_days_to_display_message
        #    "target" : {
        #      "type" : "channel" (or "guild")
        #      "id" : "target_id"
        #  },
        #  ...
        #}
        self.prefaces = [
            "*On the menu for today...*",
            "*Daily digest*",
            "*Today, we've got:*",
            "*The {server_name} Times*",
            "*Stay up to date!*",
            "*{channel_name} - {day} edition*",
            "*What's New In {channel_name}*"]
        self.time_of_day = int(self.settings.get('timeOfDay'))
        self.last_day = datetime.now().day
        self.fb_access_token = None

    @commands.group(pass_context=True)
    async def digest(self, ctx):
        """Post the digest to the current channel"""
        if ctx.invoked_subcommand is None:
            await self._digest(ctx.message.channel)
    
    @digest.command(pass_context=True)
    @checks.mod_or_permissions()
    async def enable(self, ctx):
        self._toggle(ctx.message.channel.id, 1)
        await self.bot.say("Digests enabled")

    @digest.command(pass_context=True)
    @checks.mod_or_permissions()
    async def disable(self, ctx):
        self._toggle(ctx.message.channel.id, 0)
        await self.bot.say("Digests diabled")

    @digest.command(pass_context=True)
    async def add(self, ctx, *, text : str):
        """Add a new message to the digest, expires after one day
        Only allows additions to digest-enabled channels to avoid spam"""
        if re.match("^[Ii] ", text):
            text = ctx.message.author.name + text[1:]
        if re.search(" [Ii] ", text):
            re.sub(r' [Ii] ', ' '+ctx.message.author.name+' ', text)
        if self._is_toggled(ctx.message.channel.id):
            self._add_digest(user_id=ctx.message.author.id,
                    message=text, 
                    life=1,
                    target_type="channel",
                    target_id=ctx.message.channel.id)
            await self.bot.say("One-time message added. Use `~digest check` to change its expiration date if necessary.")
        else:
            await self.bot.say("Sorry, but this channel isn't digest-enabled.")

    @digest.command(pass_context=True)
    async def check(self, ctx):
        """Allow users to edit or remove their own digests"""
        digests = []
        for digest in self.digests:
            if digest['user'] == ctx.message.author.id:
                digests.append(digest)
        messages = self._create_messages_array(ctx.message.author.id)
        prompt = await self.bot.say(self._create_prompt(ctx.message.server.channels, digests))
        # Loop message picker until the user is finished
        while True:
            try:
                choice = await self.bot.wait_for_message(timeout=60, author=ctx.message.author)
                choice = choice.content
            except:
                await self.bot.edit_message(prompt, "Cancelled.")
                return
            if re.compile("\d+").match(choice):
                try:
                    await self._edit_remove(prompt, messages[int(choice)][1], ctx.message)
                except IndexError:
                    pass
            elif choice == "quit":
                await self.bot.delete_message(prompt)
                return
            await self.bot.edit_message(prompt, self._create_prompt(ctx.message.server.channels, digests))
            messages = self._create_messages_array(ctx.message.author.id)

    @commands.group(pass_context=True)
    async def digestset(self, ctx):
        """Handle manually updating the digest image or messages"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @digestset.command(pass_context=True)
    async def banner(self, ctx, token : str=None):
        """Update the banner image. Requires a valid Facebook User Access Token
        (https://developers.facebook.com/tools/explorer)
        The same banner will be used for the entire guild"""
        if token is not None:
            await self.bot.delete_message(ctx.message)
            self.fb_access_token = token
        resp = requests.get(FB_GROUP_URL.format(self.fb_access_token), timeout=0.5).json()
        if resp.get('error'):
            await self.bot.say("Tried to connect to Facebook, but I had an invalid token")
            return
        picId = resp.get('cover').get('id')
        resp = requests.get(FB_BANNER_URL.format(picId, self.fb_access_token), timeout=0.5).json()
        await self.bot.say("The digest banner is being updated to: "+resp['images'][0]['source'])
        wget.download(url=resp['images'][0]['source'], out='data/digest/new_banner.jpg')
        os.remove('data/digest/banner.jpg')
        os.rename('data/digest/new_banner.jpg', 'data/digest/banner.jpg')

    @checks.mod_or_permissions()
    @digestset.command(pass_context=True)
    async def create(self, ctx, *, message : str):
        """Allow admins to add digests and set their scope(s), including global"""
        prompt = await self.bot.say("Which channel(s) should this digest appear in? Please type a comma-separated list for multiple channels (e.g. general, serious, off-topic), or type \"ALL\" to apply this digest to all digest-enabled channels.")
        try:
            channels = await self.bot.wait_for_message(timeout=90, author=ctx.message.author)
            channels = channels.content
        except:
            await self.bot.edit_message(prompt, "Cancelled.")
            return
        if channels == "ALL":
            self._add_digest(user_id=ctx.message.author.id,
                    message=message, 
                    life=None,
                    target_type="guild",
                    target_id=ctx.message.server.id)
            return
        channel_ids = []
        for channel_name in channels.split(","):
            channel = discord.utils.find(lambda c: c.name == channel_name.strip(), ctx.message.server.channels)
            if channel is not None:
                self._add_digest(user_id=ctx.message.author.id,
                        message=message, 
                        life=None,
                        target_type="channel",
                        target_id=channel.id)
        await self.bot.say("Digest created")
    
    @checks.mod_or_permissions()
    @digestset.command(pass_context=True)
    async def edit(self, ctx):
        """Edit/Remove messages from the digest"""
        # Show all messages by channel
        messages = self._create_messages_array()
        prompt = await self.bot.say(self._create_prompt(ctx.message.server.channels, self.digests))
        # Loop message picker until the user is finished
        while True:
            try:
                choice = await self.bot.wait_for_message(timeout=60, author=ctx.message.author)
                choice = choice.content
            except:
                await self.bot.edit_message(prompt, "Cancelled.")
                return
            if re.compile("\d+").match(choice):
                try:
                    await self._edit_remove_promote(prompt, messages[int(choice)][1], ctx.message)
                except IndexError:
                    print("digestset edit - tried to choose index that did not exist")
                    pass
            elif choice == "quit":
                await self.bot.delete_message(prompt)
                return
            await self.bot.edit_message(prompt, self._create_prompt(ctx.message.server.channels, self.digests))
            messages = self._create_messages_array()
    
    async def _digest(self, channel : discord.Channel):
        # Check channel for past digests (within last 50 messges) and delete them
        await self._delete_previous_digest(channel)
        # Get messages
        messages = self._get_messages(channel_id=channel.id, server_id=channel.server.id)
        if len(messages) == 0:
            blurb = choice(["", "", "", "", "", "You can use `~digest add` with a message and it will be added here automatically!", "You can use `~digest add` with a message and it will be added here automatically!", "If you need to add a message here that shows up over many days, use `~digest check` after you've used `~digest add`, to set a custom expiration date."])
            await self._post_digest(True, channel, blurb)
            return
        # Set preface
        message = choice(self.prefaces).format(
                server_name=channel.server.name, 
                channel_name=channel.name, 
                day=datetime.today().strftime("%B %d")) + "\n"
        for entry in messages:
            message = message + "- " + entry + "\n"
        await self._post_digest(True, channel, message)

    def _decrement_digest_life(self):
        # Decrement digest.life and remove the digest if its life reaches 0
        for digest in self.digests:
            if digest['life'] is not None:
                digest['life'] -= 1
                if digest['life'] <= 0:
                    self.digests.remove(digest)
        dataIO.save_json("data/digest/digests.json", self.digests)
        return

    async def _delete_previous_digest(self, channel : discord.Channel):
        """Try to find and delete the last digest send by the bot"""
        def check(m):
            if m.author.id != self.bot.user.id:
                return False
            elif content_match(m.attachments):
                return True
            return False

        def content_match(attachments):
            for attachment in attachments:
                if "banner" in attachment.get('url', ""):
                    return True
            return False
        
        async for message in self.bot.logs_from(channel, limit=50):
            if check(message):
                await self.bot.delete_message(message)
                return

    async def _post_digest(self, image_toggle : bool, channel : discord.Channel, message : str):
        """Actually send the message, with the banner image, to the specified channel"""
        if image_toggle:
            with open('data/digest/banner.jpg', 'rb') as f:
                await self.bot.send_file(destination=channel, fp=f, content=message)
        else:
            await self.bot.send_message(destination=channel, content=message)

    def _toggle(self, channel_id : str, toggle : int):
        self.active_channels[channel_id] = toggle
        dataIO.save_json('data/digest/active_channels.json', self.active_channels)
        return

    def _is_toggled(self, channel_id : str):
        value = self.active_channels.get(channel_id)
        if value is None:
            return 0
        return value

    def _create_messages_array(self, user_id=None):
        """Create an array of tuples, to index messages during editing
           Scoped to digests owned by user_id, or all digests if none provided"""
        m = []
        i = 0
        for digest in self.digests:
            if user_id is not None and digest['user'] == user_id:
                m.append((i, digest))
                i+=1
            else:
                m.append((i, digest))
                i+=1
        return m

    def _create_prompt(self, channels: list, digests : list):
        """Creates the message prompt to show all the active digests.
        Requires the list of channels be passed in"""
        i = 0
        message = "```\n"
        for digest in digests:
            target_type = digest['target']['type']
            target_id = digest['target']['id']
            if target_type == "guild":
                target_name = "ALL"
            elif target_type == "channel":
                channel = discord.utils.find(lambda c: c.id == target_id, channels)
                if channel is None:
                    target_name = "orphaned channel"
                else:
                    target_name = channel.name
            message += str(i) + ": " + digest['message'] + " (" + target_name + ")\n"
            i += 1
        message += "```\nSay the number of the message to edit/remove, or 'quit' to quit."
        return message

    async def _edit_remove_promote(self, prompt : str, digest : dict, message : discord.Message):
        #def is_privileged():
        #    mod_role = settings.get_server_mod(server).lower()
        #    admin_role = settings.get_server_admin(server).lower()
        #    return role_or_permissions(ctx, lambda r: r.name.lower() in (mod_role,admin_role), **perms)

        author = message.author
        await self.bot.edit_message(prompt, "Type edit to edit the digest contents, time to change an expiration date, delete to delete, or promote to show this digest to all channels.\n`"+digest['message']+"`")
        await self.bot.edit_message(prompt, "Type edit to edit the digest contents, time to change an expiration date, or delete to delete.\n`"+digest['message']+"`")
        try:
            choice = await self.bot.wait_for_message(timeout=90, author=author)
            choice = choice.content
        except:
            return
        if choice.lower() == "edit":
            # Get the new digest message, delete the old one and insert the new one
            await self.bot.edit_message(prompt, "What should this digest say?\n`"+digest['message']+"`")
            try:
                new_digest = await self.bot.wait_for_message(timeout=120, author=author)
                new_message = new_digest.content
            except:
                return
            self.digests.remove(digest)
            digest['message'] = new_message
            self.digests.append(digest)
        elif choice.lower() == "time":
            x = str(digest['life']) if digest['life'] is not None else "indefinitely"
            await self.bot.edit_message(prompt, "This digest is set to show for " + x + " more days. Type a new number to set the digest's lifespan directly, or use '+' or '-' to adjust relatively.")
            try:
                choice = await self.bot.wait_for_message(timeout=30, author=author)
                choice = choice.content
            except:
                return
            num = int(re.search('\d+', choice).group())
            life = digest['life'] if digest['life'] is not None else 0
            if "+" in choice:
                life += num
            elif "-" in choice:
                life -= num
            else:
                life = num
            digest['life'] = life
        elif choice.lower() == "delete":
            # Delete the digest
            self.digests.remove(digest)
        elif choice.lower() == "promote":
            # Delete all instances of this messge and add a new one at guild-level
            self._delete_digest_by_value(digest['message'])
            digest['target']['type'] = "guild"
            digest['target']['id'] = message.server.id
            self.digests.append(digest)
        dataIO.save_json("data/digest/digests.json", self.digests)
        return

    async def _edit_remove(self, prompt : str, digest : dict, message : discord.Message):
        author = message.author
        await self.bot.edit_message(prompt, "Type edit to edit the digest contents, time to change an expiration date, or delete to delete.\n`"+digest['message']+"`")
        try:
            choice = await self.bot.wait_for_message(timeout=90, author=author)
            choice = choice.content
        except:
            return
        if choice.lower() == "edit":
            # Get the new digest message, delete the old one and insert the new one
            await self.bot.edit_message(prompt, "What should this digest say?\n`"+digest['message']+"`")
            try:
                new_digest = await self.bot.wait_for_message(timeout=120, author=author)
                new_message = new_digest.content
            except:
                return
            self.digests.remove(digest)
            digest['message'] = new_message
            self.digests.append(digest)
        elif choice.lower() == "time":
            x = str(digest['life']) if digest['life'] is not None else "indefinitely"
            await self.bot.edit_message(prompt, "This digest is set to show for " + x + " more days. Type a new number to set the digest's lifespan directly, or use '+' or '-' to adjust relatively.")
            try:
                choice = await self.bot.wait_for_message(timeout=30, author=author)
                choice = choice.content
            except:
                return
            num = int(re.search('\d+', choice).group())
            life = digest['life'] if digest['life'] is not None else 0
            if "+" in choice:
                life += num
            elif "-" in choice:
                life -= num
            else:
                life = num
            digest['life'] = life
        elif choice.lower() == "delete":
            # Delete the digest
            self.digests.remove(digest)
        dataIO.save_json("data/digest/digests.json", self.digests)
        return

    def _add_digest(self, user_id : str, message : str, life : int, target_type : str, target_id : str):
        """Create and commit a new digest"""
        digest = {
                "user" : user_id,
                "message" : message,
                "life" : life,
                "target" : {
                    "id" : target_id,
                    "type" : target_type
                    }
                }
        self.digests.append(digest)
        dataIO.save_json("data/digest/digests.json", self.digests)

    def _get_messages(self, channel_id : str, server_id : str):
        """For a channel and server, retrieve all applicable digest messages"""
        messages = []
        for digest in self.digests:
            t_id = digest['target']['id']
            t_type = digest['target']['type']
            if (t_type == "guild" and t_id == server_id) or (t_type == "channel" and t_id == channel_id):
                messages.append(digest['message'])
        return messages

    def _delete_digest_by_value(self, message : str):
        """Delete all digests associated with the specified message text"""
        for digest in self.digests:
            if digest['message'] == message:
                try:
                    self.digests.remove(digest)
                except ValueError:
                    pass

    async def daily_digest(self):
        """Coroutine scheduled by the Cog to post the digest around a specific time of day"""
        def is_new_day(last_day):
            if last_day != datetime.now().day:
                return True
            return False

        while self is self.bot.get_cog("Digest"):
            now = int(datetime.now().strftime("%H%M"))
            if self.time_of_day <= now and is_new_day(self.last_day):
                for chan_id in self.active_channels:
                    try:
                        channel = discord.utils.find(lambda c: c.id == chan_id, self.bot.get_all_channels())
                        await self._digest(channel)
                    except:
                        pass
                self.last_day = datetime.now().day
                self._decrement_digest_life()
            await asyncio.sleep(60*15) # 15 minutes

def check_folders(resources_folder):
    if not os.path.exists(resources_folder):
        print("Creating digest data folder...")
        os.makedirs(resources_folder)

def check_files(resources_folder):
    settings = resources_folder+"settings.json"
    digests  = resources_folder+"digests.json"
    active   = resources_folder+'active_channels.json'
    if not dataIO.is_valid_json(settings):
        print("Creating empty "+str(settings)+"...")
        dataIO.save_json(settings, {
            "timeOfDay" : "0800" #stored in 24-hour time (HHMM)
        })
    if not dataIO.is_valid_json(digests):
        print("Creating default "+str(digests)+"...")
        dataIO.save_json(digests, []) 
    if not dataIO.is_valid_json(active):
        print("Creating default "+str(active)+"...")
        dataIO.save_json(active, {}) 

def setup(bot):
    resources_folder = "data/digest/"
    check_folders(resources_folder)
    check_files(resources_folder)
    n = Digest(bot)
    loop = asyncio.get_event_loop()
    loop.create_task(n.daily_digest())
    bot.add_cog(n)

