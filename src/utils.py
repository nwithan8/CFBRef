import logging.handlers
import random
import re
import copy
import urllib.parse
import urllib.request
from datetime import datetime
from datetime import timedelta

import globals
import wiki
import reddit
import classes
import index
import string_utils
import file_utils
from classes import HomeAway
from classes import Action
from classes import Play
from classes import Result
from classes import QuarterType
from classes import DriveSummary

log = logging.getLogger("bot")


def startGame(homeTeam, awayTeam, startTime=None, location=None, station=None, homeRecord=None, awayRecord=None):
	log.debug("Creating new game between {} and {}".format(homeTeam, awayTeam))

	result = verifyTeams([homeTeam, awayTeam])
	if result is not None:
		log.debug("Coaches not verified, {}".format(result))
		return "Something went wrong, someone is no longer an acceptable coach. Please try to start the game again"

	homeTeam = wiki.getTeamByTag(homeTeam.lower())
	awayTeam = wiki.getTeamByTag(awayTeam.lower())

	game = newGameObject(homeTeam, awayTeam)
	if startTime is not None:
		game.startTime = startTime
	if location is not None:
		game.location = location
	if station is not None:
		game.station = station
	if homeRecord is not None:
		homeTeam.record = homeRecord
	if awayRecord is not None:
		awayTeam.record = awayRecord

	gameThread = string_utils.renderGame(game)
	gameTitle = "[GAME THREAD] {}{} @ {}{}".format(
		"{} ".format(string_utils.unescapeMarkdown(awayRecord)) if awayRecord is not None else "",
		game.away.name,
		"{} ".format(string_utils.unescapeMarkdown(homeRecord)) if homeRecord is not None else "",
		game.home.name)

	threadID = str(reddit.submitSelfPost(globals.SUBREDDIT, gameTitle, gameThread))
	game.thread = threadID
	log.debug("Game thread created: {}".format(threadID))

	index.addNewGame(game)

	for user in game.home.coaches:
		log.debug("Coach added to home: {}".format(user))
	for user in game.away.coaches:
		log.debug("Coach added to away: {}".format(user))

	log.debug("Game started, posting coin toss comment")
	message = "{}\n\n" \
			  "The game has started! {}, you're home. {}, you're away, call **heads** or **tails** in the air." \
		.format(wiki.intro, string_utils.getCoachString(game, True), string_utils.getCoachString(game, False))
	sendGameComment(game, message, getActionTable(game, Action.COIN))
	log.debug("Comment posted, now waiting on: {}".format(game.status.waitingId))
	updateGameThread(game)

	log.debug("Returning game started message")
	return "Game started. Find it [here]({}).".format(string_utils.getLinkToThread(threadID))


def getActionTable(game, action):
	return {'action': action, 'thread': game.thread}


def verifyTeams(teamTags):
	teamSet = set()
	for i, tag in enumerate(teamTags):
		if tag in teamSet:
			log.debug("Teams are the same")
			return "You can't have a team play itself"
		teamSet.add(tag)

		team = wiki.getTeamByTag(tag)
		if team is None:
			homeAway = 'home' if i == 0 else 'away'
			log.debug("{} is not a valid team".format(homeAway))
			return "The {} team is not valid".format(homeAway)

		existingGame = index.getGameFromTeamTag(tag)
		if existingGame is not None:
			log.debug("{} is already in a game".format(tag))
			return "The team {} is already in a [game]({})".format(tag, string_utils.getLinkToThread(existingGame.thread))

	return None


def paste(title, content):  # used for posting a new paste
	pastebin_vars = dict(
		api_option='paste',
		api_dev_key=globals.PASTEBIN_KEY,
		api_paste_name=title,
		api_paste_code=content,
	)
	return urllib.request.urlopen('http://pastebin.com/api/api_post.php',
								  urllib.parse.urlencode(pastebin_vars).encode('utf8')).read()


def coinToss():
	return random.choice([True, False])


def playNumber():
	return random.randint(0, 1500)


def gameSortValue(game):
	return game.status.quarter * 1000 + game.status.clock


def updateGameThread(game):
	if game.thread is None:
		log.error("No thread ID in game when trying to update")
	game.dirty = False
	file_utils.saveGameObject(game)
	threadText = string_utils.renderGame(game)
	reddit.editThread(game.thread, threadText)


def coachHomeAway(game, coach):
	if coach.lower() in game.home.coaches:
		return HomeAway(True)
	elif coach.lower() in game.away.coaches:
		return HomeAway(False)
	else:
		return None


def sendGameMessage(isHome, game, message, dataTable):
	reddit.sendMessage(game.team(isHome).coaches,
					   "{} vs {}".format(game.home.name, game.away.name),
					   string_utils.embedTableInMessage(message, dataTable))
	return reddit.getRecentSentMessage().id


def sendGameComment(game, message, dataTable=None, saveWaiting=True):
	commentResult = reddit.replySubmission(game.thread, string_utils.embedTableInMessage(message, dataTable))
	if saveWaiting:
		setWaitingId(game, commentResult.fullname)
	log.debug("Game comment sent, now waiting on: {}".format(game.status.waitingId))
	return commentResult


def getRange(rangeString):
	rangeEnds = re.findall('(\d+)', rangeString)
	if len(rangeEnds) < 2 or len(rangeEnds) > 2:
		return None, None
	return int(rangeEnds[0]), int(rangeEnds[1])


def getPrimaryWaitingId(waitingId):
	lastComma = waitingId.rfind(",")
	if lastComma == -1:
		return waitingId
	else:
		return waitingId[lastComma + 1:]


def clearReturnWaitingId(game):
	game.status.waitingId = re.sub(",?return", "", game.status.waitingId)


def resetWaitingId(game):
	game.status.waitingId = ""


def addWaitingId(game, waitingId):
	if game.status.waitingId == "":
		game.status.waitingId = waitingId
	else:
		game.status.waitingId = "{},{}".format(game.status.waitingId, waitingId)


def setWaitingId(game, waitingId):
	resetWaitingId(game)
	addWaitingId(game, waitingId)


def isGameWaitingOn(game, user, action, messageId, forceCoach=False):
	if game.status.waitingAction != action:
		log.debug("Not waiting on {}: {}".format(action.name, game.status.waitingAction.name))
		return "I'm not waiting on a '{}' for this game, are you sure you replied to the right message?".format(
			action.name.lower())

	if not forceCoach:
		if (game.status.waitingOn == 'home') != coachHomeAway(game, user):
			log.debug("Not waiting on message author's team")
			return "I'm not waiting on a message from you, are you sure you responded to the right message?"

	if messageId not in game.status.waitingId:
		log.debug("Not waiting on message id: {} : {}".format(game.status.waitingId, messageId))

		primaryWaitingId = getPrimaryWaitingId(game.status.waitingId)
		link = string_utils.getLinkFromGameThing(game.thread, primaryWaitingId)

		if messageId.startswith("t1"):
			messageType = "comment"
		elif messageId.startswith("t4"):
			messageType = "message"
		else:
			return "Something went wrong. Not valid: {}".format(primaryWaitingId)

		return "I'm not waiting on a reply to this {}. Please respond to this {}".format(messageType, link)

	return None


def sendDefensiveNumberMessage(game):
	defenseHomeAway = game.status.possession.negate()
	log.debug("Sending get defence number to {}".format(string_utils.getCoachString(game, defenseHomeAway)))
	results = reddit.sendMessage(recipients=game.team(defenseHomeAway).coaches,
						subject="{} vs {}".format(game.away.name, game.home.name),
						message=string_utils.embedTableInMessage(
							"{}\n\nReply with a number between **1** and **1500**, inclusive.\n\nYou have until {}."
								.format(
								string_utils.getCurrentPlayString(game),
								string_utils.renderDatetime(game.playclock)
							),
							getActionTable(game, game.status.waitingAction)
						))
	resetWaitingId(game)
	for message in results:
		addWaitingId(game, message.fullname)
	log.debug("Defensive number sent, now waiting on: {}".format(game.status.waitingId))


def extractPlayNumber(message):
	numbers = re.findall('(\d+)', message)
	if len(numbers) < 1:
		log.debug("Couldn't find a number in message")
		return -1, "It looks like you should be sending me a number, but I can't find one in your message."
	if len(numbers) > 1:
		log.debug("Found more than one number")
		return -1, "It looks like you puts more than one number in your message"

	number = int(numbers[0])
	if number < 1 or number > 1500:
		log.debug("Number out of range: {}".format(number))
		return -1, "I found {}, but that's not a valid number.".format(number)

	return number, None


def setLogGameID(threadId, game):
	globals.game = game
	globals.logGameId = " {}:".format(threadId)


def clearLogGameID():
	globals.game = None
	globals.logGameId = ""


def findKeywordInMessage(keywords, message):
	found = []
	for keyword in keywords:
		if isinstance(keyword, list):
			for actualKeyword in keyword:
				if actualKeyword in message:
					found.append(keyword[0])
					break
		else:
			if keyword in message:
				found.append(keyword)

	if len(found) == 0:
		return 'none'
	elif len(found) > 1:
		log.debug("Found multiple keywords: {}".format(', '.join(found)))
		return 'mult'
	else:
		return found[0]


def addStatRunPass(game, runPass, amount):
	if runPass == Play.RUN:
		addStat(game, 'yardsRushing', amount)
	elif runPass == Play.PASS:
		addStat(game, 'yardsPassing', amount)
	else:
		log.warning("Error in addStatRunPass, invalid play: {}".format(runPass))


def addStat(game, stat, amount, offenseHomeAway=None):
	if offenseHomeAway is None:
		offenseHomeAway = game.status.possession
	log.debug(
		"Adding stat {} : {} : {} : {}".format(stat, offenseHomeAway, getattr(game.status.stats(offenseHomeAway), stat),
											   amount))
	setattr(game.status.stats(offenseHomeAway), stat, getattr(game.status.stats(offenseHomeAway), stat) + amount)
	if stat in ['yardsPassing', 'yardsRushing']:
		game.status.stats(offenseHomeAway).yardsTotal += amount


def isGameOvertime(game):
	return game.status.quarterType in [QuarterType.OVERTIME_NORMAL, QuarterType.OVERTIME_TIME]


def cycleStatus(game, messageId):
	oldStatus = copy.deepcopy(game.status)
	oldStatus.messageId = messageId
	game.previousStatus.insert(0, oldStatus)
	if len(game.previousStatus) > 5:
		game.previousStatus.pop()


def revertStatus(game, index):
	game.status = game.previousStatus[index]


def newGameObject(home, away):
	return classes.Game(home, away)


def newDebugGameObject():
	home = classes.Team(tag="team1", name="Team 1", offense=classes.OffenseType.OPTION,
						defense=classes.DefenseType.THREE_FOUR)
	home.coaches.append("watchful1")
	away = classes.Team(tag="team2", name="Team 2", offense=classes.OffenseType.SPREAD,
						defense=classes.DefenseType.FOUR_THREE)
	away.coaches.append("watchful12")
	return classes.Game(home, away)


def endGame(game, winner, postThread=True):
	game.status.quarterType = QuarterType.END
	game.status.waitingAction = Action.END
	game.status.winner = winner
	if game.status.down > 4:
		game.status.down = 4
	index.endGame(game)

	if postThread:
		postGameThread = string_utils.renderPostGame(game)
		winnerHome = True if game.status.winner == game.home.name else False
		gameTitle = "[POST GAME THREAD] {} defeats {}, {}-{}".format(
			game.team(winnerHome).name,
			game.team(not winnerHome).name,
			game.status.state(winnerHome).points,
			game.status.state(not winnerHome).points
		)
		threadID = str(reddit.submitSelfPost(globals.SUBREDDIT, gameTitle, postGameThread))

		return "[Post game thread]({}).".format(string_utils.getLinkToThread(threadID))
	else:
		return None


def pauseGame(game, hours):
	game.playclock = datetime.utcnow() + timedelta(hours=hours)
	game.deadline = game.deadline + timedelta(hours=hours)


def setGamePlayed(game):
	game.playclock = datetime.utcnow() + timedelta(hours=24)
	game.playclockWarning = False


driveEnders = [Result.TURNOVER, Result.TOUCHDOWN, Result.TURNOVER_TOUCHDOWN, Result.FIELD_GOAL, Result.PUNT]


def getDrives(game):
	drives = []
	drive = None
	for i, playSummary in enumerate(game.status.plays):
		# if playSummary in classes.kickoffPlays:

		# if playSummary not in classes.kickoffPlays and playSummary.posHome != previousPlay.posHome:

		if drive is None:
			drive = DriveSummary()
			drive.posHome = playSummary.posHome
		if playSummary.yards is not None:
			drive.yards += playSummary.yards
		drive.time += playSummary.time

		if playSummary.result in driveEnders:
			drives.append(drive)
			print(drive)
			drive = None

		previousPlay = playSummary
