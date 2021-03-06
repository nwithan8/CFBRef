import logging.handlers
import pickle
import os
import traceback

import globals

log = logging.getLogger("bot")


def saveGameObject(game):
	file = open("{}/{}".format(globals.SAVE_FOLDER_NAME, game.thread), 'wb')
	pickle.dump(game, file)
	file.close()


def loadGameObject(threadID):
	try:
		file = open("{}/{}".format(globals.SAVE_FOLDER_NAME, threadID), 'rb')
	except FileNotFoundError as err:
		log.warning("Game file doesn't exist: {}".format(threadID))
		return None
	game = pickle.load(file)
	file.close()
	return game


def archiveGameFile(threadID):
	log.debug("Archiving game: {}".format(threadID))
	try:
		os.rename("{}/{}".format(globals.SAVE_FOLDER_NAME, threadID), "{}/{}".format(globals.ARCHIVE_FOLDER_NAME, threadID))
	except Exception as err:
		log.warning("Can't archive game file: {}".format(threadID))
		log.warning(traceback.format_exc())
		return False
	return True
