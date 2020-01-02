import discord
import requests
import random
from discord.ext import commands

class Memes:
    """Post Image Memes"""

    def __init__(self, bot):
        self.bot = bot
        self.headers = {'Authorization': 'Client-ID your_client_id_here'} 

    @commands.command()
    async def viper(self):
        """Posts a viper meme"""
        resp = requests.get("https://api.imgur.com/3/album/wM1Tq/images", headers=self.headers, timeout=2).json()
        await self.bot.say(random.choice(resp['data'])['link'])

    @commands.command()
    async def pup(self):
        """Posts an NC Melee pup"""
        resp = requests.get("https://api.imgur.com/3/album/fvccvKG/images", headers=self.headers, timeout=3).json()
        await self.bot.say(random.choice(resp['data'])['link'])

    @commands.command()
    async def kitty(self):
        """Posts an NC Melee kitty"""
        resp = requests.get("https://api.imgur.com/3/album/jT36sBx/images", headers=self.headers, timeout=3).json()
        await self.bot.say(random.choice(resp['data'])['link'])

    @commands.command(pass_context=True)
    async def hornet(self, ctx):
        """GIT GUD"""
        with open('data/memes/hornet.png', 'rb') as f:
            await self.bot.send_file(ctx.message.channel, f)

    @commands.command(pass_context=True)
    async def yay(self, ctx):
        """doens't count"""
        with open('data/memes/doenst.png', 'rb') as f:
            await self.bot.send_file(ctx.message.channel, f)

    @commands.command(name="lex", pass_context=True)
    async def lex(self, ctx):
        """Trunks"""
        with open('data/memes/lex.png', 'rb') as f:
            await self.bot.send_file(ctx.message.channel, f)

    @commands.command(name="king", pass_context=True)
    async def king(self, ctx):
        """Keyblade master"""
        with open('data/memes/wills.png', 'rb') as f:
            await self.bot.send_file(ctx.message.channel, f)
    
    @commands.command(pass_context=True)
    async def collin(self, ctx):
        """F this"""
        await self.bot.say("https://gfycat.com/AffectionateGenerousBarebirdbat")

    @commands.group(pass_context=True)
    async def smith(self, ctx):
        """Smiff"""
        if ctx.invoked_subcommand is None:
            await self.bot.say("https://gfycat.com/WideeyedLazyGoldfish")

    @smith.command(pass_context=True)
    async def dance(self):
        await self.bot.say("https://gfycat.com/WideeyedLazyGoldfish")

    @smith.command(pass_context=True)
    async def crab(self):
        """Crabwalk"""
        await self.bot.say("https://gfycat.com/DirtyTartChinesecrocodilelizard")

    @commands.command(pass_context=True)
    async def savestate(self, ctx):
        """Absolute garbage"""
        with open('data/memes/nugs.jpg', 'rb') as f:
            await self.bot.send_file(ctx.message.channel, f)

    @commands.command(pass_context=True)
    async def bodied(self, ctx):
        with open('data/memes/bodied.gif', 'rb') as f:
            await self.bot.send_file(ctx.message.channel, f)

def setup(bot):
    bot.add_cog(Memes(bot))
