import discord
from discord.ext import commands

class Memes:
    """Post Image Memes"""

    def __init__(self, bot):
        self.bot = bot

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

    @commands.group(name="smith", pass_context=True)
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

def setup(bot):
    bot.add_cog(Memes(bot))

