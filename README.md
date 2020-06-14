# anki-voice

Review Anki flash cards using voice commands.  This is a currently a standalone tool (*not* an Anki plugin).

## Key Benefits

1. Hands-free flash card review.
2. When combined with external text-to-speech modules it can also be used for on-the-go, screen-free review (e.g., through bluetooth headphones).
3. Voice command recognition is all offline, so no costly cloud API services.
4. No operating system-specific dependencies, it's just Python.

## Getting Started

These instructions will get you a copy of `anki-voice` up and running on your local machine.

`anki-voice` has been tested on OSX (Catalina) and Linux (Debian buster).

### (1) Python Dependencies

`anki-voice` requires Python 3 (tested with 3.8), and multiple non-standard modules that can be installed using pip with:

```
pip3 install vosk pyaudio pyttsx3
```

The module `vosk` is used for (offline) speech-to-text (speech recognition), `pyaudio` for audio capture, and `pyttsx3` for text-to-speech.

### (2) Anki Dependencies

`anki-voice` naturally requires Anki (tested with the 2.1.x branch), but also requires the `AnkiConnect` plugin.  This plugin is used to expose an API (localhost only by default) which can be used to interact with Anki, incluing controlling the graphical user interface.

To install `AnkiConnect`, open the `Install Add-on` dialog in Anki by selecting `Tools` -> `Add-ons` -> `Get Add-ons`.  Enter the following plugin code number, and restart Anki once installation is complete.

```
2055492159 
```

For OSX users there are additional steps required to prevent Anki from sleeping when in a background state.  To prevent this, open a terminal and execute the following commands, and then restart Anki.

```
defaults write net.ankiweb.dtop NSAppSleepDisabled -bool true
defaults write net.ichi2.anki NSAppSleepDisabled -bool true
defaults write org.qt-project.Qt.QtWebEngineCore NSAppSleepDisabled -bool true
```

### (3) Vosk Dependencies

`vosk` the Python speech reconition requires a "model" to be downloaded, which represents characteristics of sounds and their relation to particular words.  Such models are trained based on a large data sample.  The creators of `vosk` have collated multiple compatible models for US English. At least one of these models must be downloaded from the following URL:

```
https://alphacephei.com/vosk/models.html
```

This should then be extracted, and the resulting folder renamed to `model` before being placed in the root of the `anki-voice` directory.  

Note that due to the short and simple nature of `anki-voice` commands (e.g., "show" or "again"), it does not necessarily mean that a larger model (with respect to file size) is more effective.  `vosk-model-en-us-daanzu-lgraph` for example works sufficiently.

## Usage

These instuctions detail how to start `anki-voice`, and the available command set. 

### Starting anki-voice

`anki-voice` is able to run directly without any arguments required. Note that it uses the default microphone for speech recognition.

```
python anki-voice.py
```

### Command Set

The following voice commands represent the minimum behaviours required to review flash cards without keyword input.  `anki-voice` requires that a Deck is manually opened for review (i.e., open to where questions are visible for review).

There can be seen to be five "core" voice commands and five "supporting".

#### Core

When presented with a flash card question the first action you're required to take is:

1. **"show"** is used to reveal the answer of a card.

The card then needs to be answered.  How this works in `anki-voice` differs a little to what is presented on the screen for multiple reasons.  Typically you'll get either three options ("again", "good", "easy") or four options ("again", "hard", "good", "easy"), which differ in both quantity and ordering (frustrating, although there is no doubt science behind it).  If you have visibility of the screen, it's easy to say the right word as a command; however, if you don't (e.g., as you're using text-to-speech for flash card content, and reviewing say, for example, through bluetooth headphones), knowing which is the right command to give can be problematic.  Due to this, users are encouraged to think of button positions as integers (one to four), which map onto the following commands:

2. **"again"** for one (always "again")
3. **"difficult"** for two.
4. **"good"** for three.
5. **"easy"** for four. If option four does not exist, this is automatically converted to three.

Numbers can't be used directly as they're typically poorly detected by speech recognition. Note also that "difficult" is used as opposed to "hard". This is because in the public models supported by vosk, "hard" requires a strong US accent to trigger. Not ideal if that is not not your accent.  The command "hard" however is supported and will work if you pronounce it in the US manner, but "difficult" should be considered the primary command.

The answer commands will not be accepted unless the answer part of the flash card is visible (i.e., they must be preceded by the "show" command).

#### Supporting

During a deck review session the following command can be used:

1. **"attach"** used to tell `anki-voice` that a new deck review session has been opened. This is an **optional** command, and is primarily used for better internal state tracking on the initially visible card.
1. **"close"** used to close the current deck review session (i.e., stop reviewing).

At any point the following commands can be used:

2. **"quit"** is used to close the `anki-voice` application.
3. **"pause"** is used to stop speech recognition so commands can be triggered (except "unpause").
4. **"close"** is used to restart speech recognition allowing any commands to be triggered.

### Adding and Altering Commands

The command set is described in the `commands.json` file.  There is a set of "primary" commands (described in the previous section), which can not be modified. However, you can also add additional words to be associated with particular commands in the `related_words` section of the JSON.  

An example of this is shown below.  Here the primary command "again" can also be invoked with "fail" or "failed". If based on your pronunciation of commands, alternative words are being understood by the speech recognition, these words can also be added here.

```
"again": {
    "related_words": [
        "fail",
        "failed"
    ]
},
```

## Troubleshooting

### "My voice commands aren't detected"

`anki-voice` uses the default microphone for speech recognition.  Verify that your default microphone is the hardware you intended, and that the microphone volume has been turned up.

### "My voice commands are being interpreted incorrectly"

`anki-voice` relies on the `vosk` model for speech recognition, which is trained specifically for US English speakers.  As such, good detection depends on your pronunciation of words. This can be a problem for British speakers, for example, due to the differences to US speakers in pronouncing "hard" (which is why "difficult" is also used in `anki-voice`).

There are three available options to resolve this.  First, modify `commands.json` to include the actual words being detected (printed to the terminal) for a particular command in the `related_words` section of the JSON. This is by far the easiest solution.  Second, search for another model. Third, train your own model.  These latter solutions are significantly more time intensive and are not suggested for standard users.

### "An AnkiConnect-specific error occured when attempting ..."

`anki-voice` typically raises this when the Anki application is not in review mode for a particular deck. Verify that the deck has been opened in the correct manner, and cards are visible for review.  Unfortunately, the `AnkiConnect` API does not expose methods for determining the "current state" of the graphical user interface, which makes accurate debug error messages challenging.

## Future Work

Although `anki-voice` functions fine as a standalone tool, ideally this would be made available as formal Anki add-on.  Through this, the dependency on AnkiConnect could also potentially be dropped.  

Additional voice commands may also be added to support behaviours such as opening alternative decks. This would provide an end-to-end voice controllable review flow.

This project arose through the idea of having flash card review skills on home assistant's (e.g., Google's Assistant or Amazon's Alexa).  Unfortunately, at the current time, the makers behind Anki forbid interaction with their web APIs in their terms of service, which is why the `AnkiConnect` plugin is a current dependency.  If such terms and conditions change, such a skill could be developed.

## Authors

* **William Knowles** - *Initial work* - [@william_knows](https://twitter.com/william_knows)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
