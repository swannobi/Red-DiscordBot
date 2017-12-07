# Strawpoll functionality by Savestate for Red-DiscordBot

import discord
from discord.ext import commands

class Strawpoll:
    """Create, link, and update live results for a Strawpoll within Discord"""

    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(pass_context=True)
    async def strawpoll(self, ctx):
        """Create and link a new Strawpoll froom user input"""
        test_embed = discord.Embed(
            title = "strawpoll embed title", type = "rich", 
            description = "strawpoll embed description", 
            url = "http://example.net", 
            colour = discord.Colour(0x206010))
        # add_field(*, name, value, inline=True)
        test_embed.add_field(name="test_inline_true", value="test_value", inline=True)
        test_embed.add_field(name="test_inline_false", value="test_value2", inline=False)
        test_embed.set_image(url="https://pbs.twimg.com/media/DQZI3ApV4AAitZc.jpg") #thanks mushbuh
        await self.bot.send_message(ctx.message.channel, content=None, embed=test_embed)
        
def setup(bot):
    bot.add_cog(Strawpoll(bot))