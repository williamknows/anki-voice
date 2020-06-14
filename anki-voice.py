__version__ = "0.3"
__author__ = "William Knowles (@william_knows)"

import argparse
from enum import Enum
import json
import logging
import os
from pathlib import Path
import pyaudio
import pyttsx3
import queue
import requests
import sys
import time
import threading
from vosk import Model, KaldiRecognizer, SetLogLevel

logging.basicConfig(level=logging.WARNING,
                    format="Logging (%(levelname)s): %(message)s",
                    handlers=[
                        logging.FileHandler("anki-voice.log"),
                        logging.StreamHandler()])

audio_feedback_queue = queue.Queue()


class AnkiActionHandler():
    """Initiates handler for sending AnkiConnect API requests based on command input."""

    def __init__(self, alert_sound_enabled=True):
        """Constructor for AnkiActionHandler class. Initialises members for tracking current
        card state, and any behavioural elements for when making AnkiConnect requests.

        Args:
            alert_sound_enabled (bool, optional): Controls confirmation sound for attach, pause, and unpause commands. Defaults to True.
        """
        # Deck context information
        self._current_state = AnkiStates.QUESTION
        # Card context information
        self._card_question = None
        self._card_answer = None
        self._card_difficult_value = 2
        self._card_good_value = 3
        # allow upscale to 4 only if required (normal behaviour)
        self._card_easy_value = 3
        # Behaviour configuration
        self._alert_sound_enabled = alert_sound_enabled

    def _send_ankiconnect_request(self, http_method, payload, error_message):
        """Handler for sening multiple types of requests to the AnkiConnect API.

        Args:
            http_method (str): The HTTP method to be used (typically either 'GET' or 'POST').
            payload (dict): The JSON to be sent to the AnkiConnect API.
            error_message (str): A request-specific message to be included in any exceptions.

        Raises:
            requests.exceptions.HTTPError: Handles HTTP-specific errors, such as a failure to connect to the AnkiConnect API.
            AnkiVoiceError: Handles anki-voice errors, in particular here for the AnkiConnect API returns a failure message.

        Returns:
            bool: Indicator of whether the request was successful
            str: The JSON response from the AnkiConnect API.
        """
        try:
            response = requests.request(
                http_method, "http://localhost:8765", json=payload)
            if response.status_code != 200:
                raise requests.exceptions.HTTPError(
                    f"Request returned non-200 status code of: {str(response.status_code)}")
            response_json = response.json()
            if (response_json["result"] == None) or response_json["result"] == False:
                raise AnkiVoiceError(
                    f"AnkiConnect returned failure status code: {str(response_json['error'])}")
        except requests.exceptions.HTTPError as ex:
            logging.error(
                f"An HTTP-related error occured when attempting to {error_message}: {ex}")
            return False, None
        except AnkiVoiceError as ex:
            logging.error(
                f"An AnkiConnect-specific error occured when attempting to {error_message}: {ex}.")
            return False, None
        except Exception as ex:
            logging.error(
                f"An unknown exception occured when attempting to {error_message}: {ex}")
            return False, None
        return True, response

    def get_current_card_information(self, called_through_attach_command=False):
        """Gets information on the current card displayed in the Anki user interface,
        such as questions, answers, and answer scales. This is also used as a handler
        for the 'attach' command.

        Args:
            called_through_attach_command (bool, optional): Indicates if it was called to handle the 'attach' command, or was called simply as a result of a new card being shown. Defaults to False.
        """
        # Request to show answer
        http_method = "GET"
        payload = {
            "action": "guiCurrentCard",
            "version": 6
        }
        error_message = "get current card information"
        success, response = self._send_ankiconnect_request(
            http_method, payload, error_message)
        # Change current context
        if success == False:
            return
        self._current_state = AnkiStates.QUESTION
        # Extract card information
        try:
            frontIsFirstCard = True
            response_json = response.json()
            if response_json["result"]["fields"]["Front"]["order"] != 0:
                frontIsFirstCard = False
            if frontIsFirstCard:
                self._card_question = response_json["result"]["fields"]["Front"]["value"]
                self._card_answer = response_json["result"]["fields"]["Back"]["value"]
            else:
                self._card_question = response_json["result"]["fields"]["Back"]["value"]
                self._card_answer = response_json["result"]["fields"]["Front"]["value"]
            self._card_difficult_value = response_json["result"]["buttons"][-1]
        except Exception as ex:
            # Reset defaults
            self._card_question = None
            self._card_answer = None
            self._card_difficult_value = 2
            # Handle exception
            logging.error(
                f"An unknown exception occured when attempting to extract card information from API response: {ex}")
            return
        # Alert only if this was an explicit "attach" command (as opposed to a new card context update)
        if called_through_attach_command:
            print("Executed: attach")
            if self._alert_sound_enabled:
                audio_feedback_queue.put_nowait("Success: Attached.")

    def show(self):
        """Reveals the answer of the current card shown within the Anki user interface."""
        # Check valid state
        if self._current_state not in [AnkiStates.QUESTION]:
            return
        # Request to show answer
        http_method = "GET"
        payload = {"action": "guiShowAnswer",
                   "version": 6
                   }
        error_message = "show a card answer"
        success, response = self._send_ankiconnect_request(
            http_method, payload, error_message)
        # Change current context
        if success:
            print("Executed: show")
            self._current_state = AnkiStates.ANSWER

    def again(self):
        """Marks the current card shown within the Anki user interface with an 'again' answer."""
        # Check valid state
        if self._current_state not in [AnkiStates.ANSWER]:
            return
        # Request to show answer
        http_method = "POST"
        payload = {
            "action": "guiAnswerCard",
            "version": 6,
            "params": {
                "ease": 1
            }
        }
        error_message = "mark card as Failed"
        success, response = self._send_ankiconnect_request(
            http_method, payload, error_message)
        # Change current context
        if success:
            print("Executed: again")
            self._current_state = AnkiStates.QUESTION
            self.get_current_card_information()

    def difficult(self):
        """
        Marks the current card shown within the Anki user interface with a 'difficult' answer.
        Note that in the user interface this is shown as 'hard'; however, the primary command
        of 'difficult' is used here as it's more successfully detected by the speech-to-text
        module.
        """
        # Check valid state
        if self._current_state not in [AnkiStates.ANSWER]:
            return
        # Request to show answer
        http_method = "POST"
        payload = {
            "action": "guiAnswerCard",
            "version": 6,
            "params": {
                "ease": self._card_difficult_value
            }
        }
        error_message = "mark card as Difficult (Hard)"
        success, response = self._send_ankiconnect_request(
            http_method, payload, error_message)
        # Change current context
        if success:
            print("Executed: difficult")
            self._current_state = AnkiStates.QUESTION
            self.get_current_card_information()

    def good(self):
        """Marks the current card shown within the Anki user interface with a 'good' answer."""
        # Check valid state
        if self._current_state not in [AnkiStates.ANSWER]:
            return
        # Request to show answer
        http_method = "POST"
        payload = {
            "action": "guiAnswerCard",
            "version": 6,
            "params": {
                "ease": self._card_good_value
            }
        }
        error_message = "mark card as Good"
        success, response = self._send_ankiconnect_request(
            http_method, payload, error_message)
        # Change current context
        if success:
            print("Executed: good")
            self._current_state = AnkiStates.QUESTION
            self.get_current_card_information()

    def easy(self):
        """Marks the current card shown within the Anki user interface with an 'easy' answer."""
        # Check valid state
        if self._current_state not in [AnkiStates.ANSWER]:
            return
        # Request to show answer
        http_method = "POST"
        payload = {
            "action": "guiAnswerCard",
            "version": 6,
            "params": {
                "ease": self._card_easy_value
            }
        }
        error_message = "mark card as Easy"
        success, response = self._send_ankiconnect_request(
            http_method, payload, error_message)
        # Change current context
        if success:
            print("Executed: easy")
            self._current_state = AnkiStates.QUESTION
            self.get_current_card_information()

    def close(self):
        """Closes the current deck review session and returns to the 'Default' Anki deck screen."""
        # Check valid state
        if self._current_state not in [AnkiStates.QUESTION, AnkiStates.ANSWER]:
            return
        # Request to close deck (returns to "Default" deck)
        http_method = "POST"
        payload = {
            "action": "guiDeckOverview",
            "version": 6,
            "params": {
                "name": "Default"
            }
        }
        error_message = "close current deck and return to default"
        success, response = self._send_ankiconnect_request(
            http_method, payload, error_message)
        # Change current context
        if success:
            print("Executed: close")
            self._current_state = AnkiStates.NONQUIZ


class AnkiSpeechToCommand():
    """ Manages speech-to-text for Anki-related commands."""

    def __init__(self, command_config="commands.json", alert_sound_enabled=True):
        """Constructor for AnkiSpeechToCommand. Initialises vosk speech-to-text module,
        AnkiConnect API handler object, and derives word commands from a JSON file.

        Args:
            command_config (str, optional): Filename for the JSON command file. Defaults to "commands.json".
            alert_sound_enabled (bool, optional): Controls confirmation sound for attach, pause, and unpause commands. Defaults to True.

        Raises:
            json.decoder.JSONDecodeError: Handles decode errors from the JSON command file, such as malformed syntax.
            AnkiVoiceError: Handles anki-voice errors, in particular here for missing command definitions.
        """
        # Verify speech-to-text engine (vosk) model exists
        if not Path(Path(__file__).resolve().parent, "Model").is_dir():
            print("Please download the model from https://github.com/alphacep/vosk-api/blob/master/doc/models.md and unpack as 'model' (directory) in the current folder.")
            sys.exit(1)
        # Configure speech-to-text engine
        SetLogLevel(-10)
        self._model = Model("model")
        self._recogniser = KaldiRecognizer(self._model, 16000)
        self._stream = pyaudio.PyAudio().open(format=pyaudio.paInt16, channels=1,
                                              rate=16000, input=True, frames_per_buffer=2048)
        self._stream.start_stream()
        # Create AnkiConnect API handler object
        self._anki_action = AnkiActionHandler(
            alert_sound_enabled=alert_sound_enabled)
        # Behaviour configuration
        self._speech_to_text_paused = False
        self._alert_sound_enabled = alert_sound_enabled
        # Parse command JSON configuation
        self.command_config_load(command_config)
        # tba
        self.engine = pyttsx3.init()

    def command_config_load(self, command_config):
        try:
            with open(command_config) as command_config_raw:
                command_config_json = json.load(command_config_raw)
                for command in ["attach", "show", "again", "difficult", "good", "easy", "pause", "unpause", "close", "quit"]:
                    if command not in command_config_json:
                        raise Exception(
                            f"Malformed commands in {command_config}. Missing the command (key): {command}")
                    if command == "attach":
                        self._attach_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "show":
                        self._show_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "again":
                        self._again_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "difficult":
                        self._difficult_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "good":
                        self._good_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "easy":
                        self._easy_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "pause":
                        self._pause_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "unpause":
                        self._unpause_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "close":
                        self._close_commands = [
                            command] + command_config_json[command]["related_words"]
                    elif command == "quit":
                        self._quit_commands = [
                            command] + command_config_json[command]["related_words"]
        except json.decoder.JSONDecodeError as ex:
            logging.error(
                f"A JSON decoder error occured when attempting to obtain Anki command words: {ex}")
            sys.exit(1)
        except AnkiVoiceError as ex:
            logging.error(
                f"An anki-voice error occured: {ex}")
            sys.exit(1)
        except Exception as ex:
            logging.error(
                f"An unknown exception occured when attempting to obtain Anki command words: {ex}")
            sys.exit(1)

    def run(self):
        """Starts thread to handle speech-to-text module functionality."""
        self._command_detection = threading.Thread(
            target=self._cyclic_word_detection)
        self._command_detection.start()

    def pause(self):
        """Pauses speech-to-text monitoring (except for 'unpause' commands)."""
        self._speech_to_text_paused = True
        print("Executed: pause")
        if self._alert_sound_enabled:
            audio_feedback_queue.put_nowait("Success: Paused.")

    def unpause(self):
        """Unpauses speech-to-text monitoring (permitting any commands)."""
        self._speech_to_text_paused = False
        print("Executed: unpause")
        if self._alert_sound_enabled:
            audio_feedback_queue.put_nowait("Success: Unpaused.")

    def quit(self):
        """Triggers exit of anki-voice."""
        print("Executed: quit")
        sys.exit(0)

    def _cyclic_word_detection(self):
        """Loops through audio input and identifies speech to text for possible commands."""
        while True:
            data = self._stream.read(2048, exception_on_overflow=False)
            if len(data) == 0:
                break
            if self._recogniser.AcceptWaveform(data):
                res = json.loads(self._recogniser.Result())
                # Identify sentence blocks
                if "text" in res:
                    detected_words = res["text"].lower()
                    if detected_words != "":
                        self._action_command(detected_words)

    def _action_command(self, detected_words):
        """Analyses speech-to-text strings for anki-voice commands.

        Args:
            detected_words (str): The words identified through speech-to-text analysis.
        """
        # Verify if paused, and if so, only proceed if command is to unpause
        if self._speech_to_text_paused:
            if detected_words not in self._unpause_commands:
                return
        # Process commands
        print("Detected:", detected_words)
        if detected_words in self._attach_commands:
            self._anki_action.get_current_card_information(
                called_through_attach_command=True)
        elif detected_words in self._show_commands:
            self._anki_action.show()
        elif detected_words in self._again_commands:
            self._anki_action.again()
        elif detected_words in self._difficult_commands:
            self._anki_action.difficult()
        elif detected_words in self._good_commands:
            self._anki_action.good()
        elif detected_words in self._easy_commands:
            self._anki_action.easy()
        elif detected_words in self._pause_commands:
            self.pause()
        elif detected_words in self._unpause_commands:
            self.unpause()
        elif detected_words in self._close_commands:
            self._anki_action.close()
        elif detected_words in self._quit_commands:
            self.quit()

    def __del__(self):
        """Destructor for AnkiSpeechToCommand. Stops pyaudio stream used by vosk speech-to-text module.

        Raises:
            AttributeError: Handles situation where "module" folder validation fails in constructor. Not required to be logged.
        """
        try:
            self._stream.stop_stream()
        except AttributeError as ex:
            pass
        except Exception as ex:
            logging.error(
                f"An unknown exception occured when attempting to stop the pyaudio stream for the vosk module: {ex}")


class AnkiStates(Enum):
    """Enum to represent different states of the Anki application user interface.

    Args:
        Enum (Enum): Inheriting from the base Enum class.
    """
    NONQUIZ = 0
    QUESTION = 1
    ANSWER = 2
    EXIT = 3


class AnkiVoiceError(Exception):
    """Exception handler specific to anki-voice.

    Args:
        Exception (Exception): Inheriting from the base Exception class.
    """

    def __init__(self, message):
        # Call the base class constructor with the parameters it needs
        super().__init__(message)


def CommandAudioFeedback():
    """Checks queue for information to speak back to user through text-to-speech."""
    while True:
        text_to_speak = audio_feedback_queue.get()
        pyttsx3.speak(text_to_speak)
        audio_feedback_queue.task_done()


def main(args):
    try:
        print("""              _    _                 _          
   __ _ _ __ | | _(_)    __   _____ (_) ___ ___ 
  / _` | '_ \\| |/ / |____\\ \\ / / _ \\| |/ __/ _ \\
 | (_| | | | |   <| |_____\\ V / (_) | | (_|  __/
  \\__,_|_| |_|_|\\_\\_|      \\_/ \\___/|_|\\___\\___| (by @william_knows)
        """)
        print("Before issuing voice commands verify that:")
        print("(1) Anki is open with the AnkiConnect plugin installed.")
        print("(2) A deck is open in review mode (i.e., question prompts are visible).")
        print("If either of these conditions are not met, errors may occur.")
        print("\nStarting up...\n")
        control = AnkiSpeechToCommand(
            command_config=args.command_config, alert_sound_enabled=args.alert_sound_disabled)
        control.run()
        print("STARTED ||||||||||||||||||||||||||||||||||||||||| REAL-TIME COMMAND LOG:\n")
        CommandAudioFeedback()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--command_config", action="store", default="commands.json",
                        required=False, help="JSON file containing command words.")
    parser.add_argument("-a", "--alert_sound_disabled", action="store_false", default=True,
                        help="Disasble sounds on context changes for: attach, pause, unpause.")
    args = parser.parse_args()

    main(args)
