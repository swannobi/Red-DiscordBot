import discord
from discord.ext import commands
import requests
import os
import re
from datetime import datetime
from datetime import timedelta
from random import randint
from cogs.utils.dataIO import dataIO
from __main__ import send_cmd_help
from .utils import checks

BASE = "https://www.smashladder.com/api/v1/"
OAUTH = "https://www.smashladder.com/oauth/token"
MELEE_ID = 2
US_ID = 225
DISCORD_REGISTRATION_CHANNEL = "8799399"

RESOURCES = "data/smashing/ladder/"

class Smashladder:
    """Integration layer between Discord and Anther's Ladder"""

    def __init__(self, bot):
        self.bot = bot
        self.token_issued = datetime.now()
        self.token = self.get_token()
        self.headers = {'Authorization':'Bearer '+self.token}
        self.current_season = self.get_current_melee_season()
        self.aliases = dataIO.load_json(RESOURCES+"aliases.json")
        self.char_icons = dataIO.load_json(RESOURCES+"../char_icons.json")
        self.melee_chars = dataIO.load_json(RESOURCES+"../melee_chars.json")

    @commands.group(pass_context=True, no_pm=False)
    async def ladder(self, ctx):
        """Use ladder commands for all Smashladder-related functionality"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @ladder.command(pass_context=True)
    @checks.admin_or_permissions(manage_server=True)
    async def reg_override(self, ctx, member : discord.Member):
        """Use this to reset a Member's registration status."""
        try:
           del self.aliases[member.id]
           dataIO.save_json(RESOURCES+"aliases.json", self.aliases)
        except Exception as e:
            print(e)
            await self.bot.say("Something went wrong... make sure you @ the right member")

    @ladder.command(pass_context=True, no_pm=False, aliases=["link"])
    async def register(self, ctx, tag : str):
        """Use this method to register a player profile on Anther's Ladder with a Member of this server."""
        # Check if player is asking for a tag that someone else has registered
        tag = re.sub(r"\s", "_", tag)
        if tag in self.aliases.values():
            await self.bot.say("This playername has already been registered. "
                    "If there is a problem, please contact an admin and ask them to use `reg_override`.")
            return
        # Check Smashladder if this player exists
        player_profile = self._player_profile(tag)
        if 'error' in player_profile:
            await self.bot.say("There's no '"+tag+"' registered on Anther's ladder")
            return
        # Generate a random 6-digit code
        code = str(randint(100000, 999999))
        # Tell the user to confirm the registration
        await self.bot.whisper("To finish registration, I need to see a message from "+tag+
                " in the Discord-Registration channel Anther's Ladder. If you haven't already, "
                "log in as "+tag+".\n\nClick here https://www.smashladder.com/netplay/8799399 "
                "to join the channel.\n\nOnce you're there, send the following code: *"+code+"*")
        await self.bot.whisper("I'll wait a few minutes and check for your message automatically, "
                "or you can DM me--just say \"done\" to force me to check immediately. "
                "If I check automatically and I don't see a code, registration will be "
                "aborted and you'll have to try again later.")
        # Handle code confirmation - if the correct code is detected, persist a relation between this
        # user's ID and the smashladder name being registered. If no code/an incorrect code is detected, return
        try:
            # Ensures the user is replying via DM
            def check(message):
                return message.channel.type == discord.ChannelType.private
            answer = await self.bot.wait_for_message(timeout=120, check=check, author=ctx.message.author)
            # Confirm result to user after they respond via DM
            if self._confirm_registration(tag, code):
                await self.bot.whisper("I see your confirmation code. You are now registered as "+tag+".")
            else:
                await self.bot.whisper("I didn't see what I expected. Ensure you're logged "
                        "in as the correct user and that you didn't mis-type the code. Please try again later.")
                return
        # Check automatically if user has not responded via DM after 120 seconds
        except:
            if self._confirm_registration(tag, code):
                await self.bot.whisper("I saw your confirmation code. You are now registered as "+tag+".")
            else:
                await self.bot.whisper("I checked automatically but didn't see a code from "+tag+
                        " in the chat. Try again later.")
                return
        # Write to json and refresh cache
        author = ctx.message.author.id
        self.aliases[author] = tag
        dataIO.save_json(RESOURCES+"aliases.json", self.aliases)

    def _confirm_registration(self, name, code):
        # Return True if there is a message of `code` from user `name` in the Smashladder chat
        chat = self._chat_messages(DISCORD_REGISTRATION_CHANNEL)
        try:
            chat_logs = chat['chat_rooms']['chat_room'][str(DISCORD_REGISTRATION_CHANNEL)]['chat_messages']
            for message in chat_logs.values():
                if message['player']['username'].lower() == name.lower() and message['message'] == code:
                    return True
            return False
        except Exception as e:
            print(e)
            return False

    @ladder.command(pass_context=True)
    async def info(self, ctx, *, player):
        """Return information about a smashladder player's league"""
        # Try to parse @mentions or member names,
        # use their Discord role color to set the color of the profile embed later
        # TODO support showing league rankings from multiple games
        color = None
        user = discord.utils.find(lambda m: m.name in player, ctx.message.server.members)
        if user is None:
            user = ctx.message.server.get_member_named(player)
        if user is not None and user.id in self.aliases.keys():
            color = user.colour
            player = self.aliases[user.id]
        # Replace whitespace with underscores so that Smashladder can find the appropriate player
        player = re.sub(r"\s", "_", player)
        # Call the API, get the player profile
        profile = self._player_profile(player)
        # Ensure we have data
        if profile.get('success') and profile.get('user'): 
            # Ensure we have Melee data
            if not profile['user']['ladder_information'].get(str(MELEE_ID)):
                await self.bot.say(embed=self._create_embed(profile['user'], "unranked in the current season", color))
                return
            league = profile['user']['ladder_information'][str(MELEE_ID)]['league']
            if league['name']:
                league_name = league['name']+" "+league['division']#+" "+str(league['points'])
                await self.bot.say(embed=self._create_embed(profile['user'], league_name, color))
            else:
                await self.bot.say(embed=self._create_embed(profile['user'], "unranked in the current season", color))
        else:
            await self.bot.say(player+" not found")

    def _get_character_name(self, character):
        """Returns a valid character name, from a stored list of aliases."""
        try:
            return self.melee_chars[re.sub(r"\s|-", "", character.lower())]
        except:
            raise KeyError("Couldn't find the character {}.".format(str(character)))

    def _create_embed(self, profile, league, color=None):
        """Goodness gracious what an ugly function"""
        ## Set join_date, locale, color, & char
        char = None
        description = None
        bad_behavior = ""
        # Join date - "full" is the datetime as a string
        join_date = profile['member_since']['full']
        # Get location information
        # First priority is "country_state", which is "Not Set" by default (and implies that other data is null) 
        if profile['location']['country_state'] == "Not Set":
            locale = "Not set"
        # "locality" is a specific region and "state" is a more general area
        elif profile['location']['locality']['name'] is not None and profile['location']['state']['name'] is not None:
            locale = profile['location']['locality']['name']+", "+profile['location']['state']['name']
        # "country_state" is used for many international locations where "state" isn't a thing
        else:
            locale = profile['location']['country_state']
        # Color was set if the player lookup has a discord Member registered to it. Use red by default
        if not color:
            if profile['glow_color']:
                color = discord.Colour(int(profile['glow_color'][1:], 16))
            else:
                color = discord.Colour.red()
        # Try to set the icon according to the player's main or most-played character
        try:
            mains = profile['ladder_information'][str(MELEE_ID)]['mains']
            chars = profile['ladder_information'][str(MELEE_ID)]['characters']
            # Bias toward "mains", which are set by the player in their profile...
            if len(mains) > 0:
                char = self._get_character_name(mains[0]['slug_name'])
            # ...whereas "characters" represent the char(s) used in recorded matches
            elif len(chars) > 0:
                char = self._get_character_name(chars[0]['slug_name'])
        except KeyError as e:
            print(e)
        # Set online status
        if 'now_playing' in profile.keys():
            if profile['now_playing']['player1']['username'] == profile['username']:
                other_player = profile['now_playing']['player2']['username']
            else:
                other_player = profile['now_playing']['player1']['username']
            description = "Playing "+profile['now_playing']['ladder_game']['name']+" with "+other_player
        elif profile['now_searching'] is not None:
            #TODO update this with game type in the search
            description = "Looking for a match... 🔎"
        # Check for toxic behavior
        if ((len(profile['reported_match_behavior']) > 0) 
             or (profile['behavior_description'] is not None
                 and profile['behavior_description']['type'] is not None
                 and profile['behavior_description']['type'] != 'good')):
                 # TODO ask Anther about behavior_descrption.type
            bad_behavior = "☣️"
        ## Create the embed with league info, color, and link to the player profile
        data = discord.Embed(title=league, colour=color, url=profile['profile_url'])
        # Set the character icon
        if char is not None:
            data.set_author(name=profile['username']+" "+bad_behavior, icon_url="https://i.imgur.com/"+self.char_icons[char]+".png")
        else:
            data.set_author(name=profile['username'])
        if description:
            data.description = description
        data.add_field(name="Joined Ladder on", value=join_date)
        data.add_field(name="Locale", value=locale, inline=True)
        data.add_field(name="Matches played", value=profile['total_matches_played'], inline=False)
        is_subbed = profile['is_subscribed']
        sub_streak = profile['subscription_streak']
        if is_subbed == 'true':
            data.add_field(name="Subbed for", value=str(sub_streak)+" months")
        data.set_footer(text="Smashladder-Discord integration by Swann")
        return data

    ### UTILITY FUNCTIONS ###

    def get_current_melee_season(self):
        """Return the id of the current active season"""
        return self._ladders_ladders()['ladders'][MELEE_ID-1]['active_season']

    def get_melee_searches(self):
        """Return active searches for melee matches"""
        searches = self._matchmaking_visible_searches()['searches']
        melee_searches = []
        for search in searches:
            if search['game_type'] == str(MELEE_ID):
                melee_searches.append(search)
        return melee_searches

    def ensure_token(self):
        """Ensure the current token is valid"""
        elapsed_time = datetime.now() - self.token_issued
        if (elapsed_time / timedelta(hours=1)) > 1:
            self.token = self.get_token()
            self.headers = {'Authorization':'Bearer '+self.token}

    def get_token(self):
        """Get a new Oauth token"""
        token = requests.post(OAUTH, data = {
                'grant_type':'client_credentials',
                'client_id':'AB39D899E871GFD4589D1G3A',
                'client_secret':'BCc1gA6cDBf908eDD34C5057A3d48aF0F2c8'
            }, timeout=1).json()['access_token']
        self.token_issued = datetime.now()
        return token

    def _chat_messages(self, chat_room_id : str):
        """API call - chat messages"""
        self.ensure_token()
        return requests.get(BASE+"chat/messages?chat_room_id="+chat_room_id, headers=self.headers, timeout=1).json()

    def _ladders_ladders(self):
        """API call - ladder info"""
        self.ensure_token()
        return requests.get(BASE+"ladders/ladders", headers=self.headers, timeout=1).json()

    def _player_profile(self, player : str):
        """API call - player profile"""
        self.ensure_token()
        return requests.get(BASE+"player/profile?username="+player, headers=self.headers, timeout=1).json()
    
    def _matchmaking_visible_searches(self):
        """API call - matchmaking visible_searches"""
        self.ensure_token()
        return requests.get(BASE+"matchmaking/visible_searches", headers=self.headers, timeout=1).json()

def check_folders():
    if not os.path.exists(RESOURCES):
        print("Creating smashladder data folder...")
        os.makedirs(RESOURCES)

def check_files():
    files = [RESOURCES+"aliases.json"]
    for path in files:
        if not dataIO.is_valid_json(path):
            print("Creating empty "+str(path)+"...")
            dataIO.save_json(path, {})    

def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(Smashladder(bot))
