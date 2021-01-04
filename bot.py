import discord
from discord.ext import commands
import aiosqlite
import sys, os
import traceback
import asyncio
import time
import random, typing
from datetime import datetime
os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True" 
os.environ["JISHAKU_HIDE"] = "True"

desc = "EconomyX is a money system for Discord. It's straightfoward with only economy related commands, to keep it simple. I was made by averwhy#3899."

class EcoBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    async def prompt(self, authorid, message: discord.Message, *, timeout=60.0, delete_after=True, author_id=None):
        """Credit to Rapptz
        https://github.com/Rapptz/RoboDanny/blob/715a5cf8545b94d61823f62db484be4fac1c95b1/cogs/utils/context.py#L93"""
        confirm = None

        for emoji in ('\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}'):
            await message.add_reaction(emoji)

        def check(payload):
            nonlocal confirm
            if payload.message_id != message.id or payload.user_id != authorid:
                return False
            codepoint = str(payload.emoji)
            if codepoint == '\N{WHITE HEAVY CHECK MARK}':
                confirm = True
                return True
            elif codepoint == '\N{CROSS MARK}':
                confirm = False
                return True
            return False

        try:
            await bot.wait_for('raw_reaction_add', check=check, timeout=timeout)
        except asyncio.TimeoutError:
            confirm = None

        try:
            if delete_after:
                await message.delete()
        finally:
            return confirm
    
    async def add_player(self,member_object):
        """Adds a player to the database"""
        try:
            await bot.db.execute("INSERT INTO e_users VALUES (?, ?, ?, 100.0, 0.0, 'FFFFFF')",(member_object.id,member_object.name,member_object.guild.id,))
            await bot.db.commit()
            return "Done! View your profile with `e$profile`"
        except Exception as e:
            return str(e)
        
    async def get_player(self,id):
        """Gets a player from the database"""
        cur = await bot.db.execute("SELECT * FROM e_users WHERE id = ?",(id,))
        data = await cur.fetchone()
        await bot.db.commit()
        return data
    
    async def get_stock(self, id):
        """Gets a stock from the database"""
        cur = await bot.db.execute("SELECT * FROM e_stocks WHERE ownerid = ?",(id,))
        data = await cur.fetchone()
        await bot.db.commit()
        return data
    
    async def begin_user_deletion(self, ctx, i_msg):
        """Begins the user deletion process."""
        player = await self.get_player(ctx.author.id)
        if player is None: return
        def check(m):
            return m.content.lower() == 'yes' and m.channel == ctx.channel and m.author == ctx.author
        user_response = await bot.wait_for('message', check=check)
        msg = await ctx.send(
"""**If you proceed, you will __permanently__ lose the following data:**
    - Your profile (money, total earned amount, custom color, etc)
    - Your invests (money invested, etc)
    - Any owned stock (The fee spent to create it, its points, etc (all investers get refunded))
*All* data involving you will be deleted.
**Are you sure you would like to continue?** ***__There is no going back.__***
""")
        did_they = await self.prompt(ctx.author.id, msg, timeout=30)
        if did_they:
            await bot.db.execute("DELETE FROM e_users WHERE id = ?",(ctx.author.id,))
            await bot.db.execute("DELETE FROM e_invests WHERE userid = ?",(ctx.author.id,))
            await bot.db.execute("DELETE FROM e_stocks WHERE ownerid = ?",(ctx.author.id,))
            await ctx.send("Ok, it's done. According to my database, you no longer exist.")
        if not did_they:
            await ctx.send("Canceled. None of your data was deleted.")
        if did_they is None: return
        await msg.delete()
        #await i_msg.delete()
        return
        
    async def usercheck(self,uid):
        """Checks if an user exists in the database"""
        cur = await bot.db.execute("SELECT * FROM e_users WHERE id = ?",(uid,))
        data = await cur.fetchone()
        return data is not None
        # False = Not in database
        # True = In database
        
    async def on_bet_win(self,member_object,amount_bet):
        """This is called when an user wins at the bet game."""
        c = await bot.db.execute("SELECT * FROM e_users WHERE id = ?",(member_object.id,))
        data = await c.fetchone()
        if data is not None:
            amount_won = amount_bet * 2
            #update user
            await bot.db.execute("UPDATE e_users SET bal = (bal + ?) WHERE id = ?",(amount_bet,member_object.id,))
            await bot.db.execute("UPDATE e_users SET totalearnings = (totalearnings + ?) WHERE id = ?",(amount_bet,member_object.id,))
            #get new data
            c = await bot.db.execute("SELECT * FROM e_users WHERE id = ?",(member_object.id,))
            await bot.db.commit()
            data2 = await c.fetchone()
            newbalance = float(data[3])
            
            return [amount_won,newbalance]
        else:
            return None
        
    async def on_bet_loss(self,member_object,amount_bet):
        """This is called when an user loses at the bet game."""
        c = await bot.db.execute("SELECT * FROM e_users WHERE id = ?",(member_object.id,))
        data = await c.fetchone()
        if data is not None:
            amount_lost = amount_bet
            #update user
            await bot.db.execute("UPDATE e_users SET bal = (bal - ?) WHERE id = ?",(amount_bet,member_object.id,))
            #get new data
            c = await bot.db.execute("SELECT * FROM e_users WHERE id = ?",(member_object.id,))
            await bot.db.commit()
            data2 = await c.fetchone()
            newbalance = float(data[3])
            
            return newbalance
        else:
            return None
    async def transfer_money(self,member_paying: typing.Union[discord.User, discord.Member] ,member_getting_paid: typing.Union[discord.User, discord.Member],amount):
        """Transfers money from one player to another."""
        c = await bot.db.execute("SELECT * FROM e_users WHERE id = ?",(member_paying.id,))
        data1 = await c.fetchone()
        c = await bot.db.execute("SELECT * FROM e_users WHERE id = ?",(member_getting_paid.id,))
        data2 = await c.fetchone()
        #update users
        await bot.db.execute("UPDATE e_users SET bal = (bal - ?) WHERE id = ?",(amount,member_paying.id,))
        await bot.db.execute("UPDATE e_users SET bal = (bal + ?) WHERE id = ?",(amount,member_getting_paid.id,))
        
        await bot.db.commit()
        
    async def get_player_color(self, memberobject):
        """Gets a players color."""
        player = await bot.get_player(memberobject.id)
        if player is None:
            return None
        else:
            return int(("0x"+player[5]),0)
        
    def utc_calc(self, timestamp: str):
        """Returns a pretty format of the amount of time ago from a given UTC Timestamp."""
        delta_uptime = datetime.utcnow() - datetime.strptime(timestamp,"%Y-%m-%d %H:%M:%S.%f")
        hours, remainder = divmod(int(delta_uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        return [days, hours, minutes, seconds]
       
            
bot = EcoBot(command_prefix=commands.when_mentioned_or("ecox ","e$"),description=desc,intents=discord.Intents(reactions=True, messages=True, guilds=True, members=True))

bot.initial_extensions = ["jishaku","cogs.player_meta","cogs.devtools","cogs.games","cogs.money_meta","cogs.misc","cogs.jobs","cogs.stocks"]
with open("TOKEN.txt",'r') as t:
    TOKEN = t.readline()
bot.time_started = time.localtime()
bot.version = '0.2.0'
bot.newstext = None
bot.news_set_by = "no one yet.."
bot.total_command_errors = 0
bot.total_command_completetions = 0
bot.launch_time = datetime.utcnow()
print(bot.launch_time)


async def startup():
    bot.db = await aiosqlite.connect('economyx.db')
    await bot.db.execute("CREATE TABLE IF NOT EXISTS e_users (id int, name text, guildid int, bal double, totalearnings double, profilecolor text, lotterieswon int)")
    await bot.db.execute("CREATE TABLE IF NOT EXISTS e_stocks (stockid int, name text, points double, previouspoints double, ownerid int, created text)")
    await bot.db.execute("CREATE TABLE IF NOT EXISTS e_invests (stockid int, userid int, invested double, stockname text, invested_at double, invested_date blob)")
    await bot.db.execute("CREATE TABLE IF NOT EXISTS e_lottery_users (userid int, amount double, boughtwhen blob)")
    await bot.db.execute("CREATE TABLE IF NOT EXISTS e_lottery_main (amountpooled double, drawingwhen blob)")
    print("Database connected")
    
    bot.backup_db = await aiosqlite.connect('ecox_backup.db')
    print("Backup database is ready")
    await bot.backup_db.close()
bot.loop.create_task(startup())

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('---------------------------------')
    
@bot.event
async def on_command_completion(command):
    await bot.db.commit() # just cuz
    bot.total_command_completetions += 1
    
@bot.event
async def on_command_error(ctx, error): # this is an event that runs when there is an error
    if isinstance(error, discord.ext.commands.errors.CommandNotFound):
        #await ctx.message.add_reaction("\U00002753") # red question mark         
        return
    elif isinstance(error, discord.ext.commands.errors.CommandOnCooldown): 
        s = round(error.retry_after,2)
        if s > 3600: # over 1 hour
            s /= 3600
            s = round(s,1)
            s = f"{s} hour(s)"
        elif s > 60: # over 1 minute
            s /= 60
            s = round(s,2)
            s = f"{s} minute(s)"
        else: #below 1 min
            s = f"{s} seconds"
        msgtodelete = await ctx.send(f"`ERROR: Youre on cooldown for {s}!`")
        await asyncio.sleep(15)
        await msgtodelete.delete()
        return
    elif isinstance(error, commands.CheckFailure):
        # these will be handled in cogs
        return
    else:
        bot.total_command_errors += 1
        await ctx.send(f"```diff\n- {error}\n```")
        # All other Errors not returned come here. And we can just print the default TraceBack.
        print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

for cog in bot.initial_extensions:
    try:
        bot.load_extension(f"{cog}")
        print(f"loaded {cog}")
    except Exception as e:
        print(f"Failed to load {cog}, error:\n", file=sys.stderr)
        traceback.print_exc()
asyncio.set_event_loop(asyncio.SelectorEventLoop())
bot.run(TOKEN, bot = True, reconnect = True)