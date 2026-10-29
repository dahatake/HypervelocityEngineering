[日本語](rpg-originality.md) | **English**

# List of originality for the RPG-style map (FR-1054 AC-293)

This is a list for confirming that the RPG-style display mode (`EABK-Studio/web/js/maprpg.js`, `rpgaudio.js`, `rpgworld.js`) does not reproduce any existing copyrighted work (the music, characters, proper names, or images of existing games, starting with Dragon Quest). The procedure for confirming is "FR-1054 AC-293" in `docs/manual-tests.md`.

## How each element is generated

| Target | How it is generated | External assets |
|---|---|---|
| Melodies (field, town, castle) | Short number sequences (semitone pitches) written in `SCENES` in `rpgaudio.js` are played with Web Audio oscillators. The sequences were created for this screen. | None (no audio files, sound sources, or libraries are fetched or bundled) |
| Sound effects (move, confirm, cancel, text advance, menu, blocked) | The note tables in `SOUND_EFFECTS` are played with oscillators | None |
| Characters (traveler, resident, guide) | `drawChar` in `maprpg.js` draws them on a Canvas by combining rectangles | None (no image files) |
| Terrain, castle, town buildings | `drawGround`, `drawCastle`, `drawHouse`, `drawDoor`, and `drawBridge` draw them with rectangles | None |
| Place names, personal names, terms | Castle and town names come from the user's managed data (purpose IDs; town names derived from entity names, and the "unrelated town"); residents' names are entity names. Characters are called by the generic words "traveler", "resident", and "guide" | None |

## Checklist (every item must be "Yes")

1. No melody copies the theme or a known melody of an existing game or piece of music (listen to them, and compare the number sequences with known melodies).
2. The sound effects are short sounds of plain square, triangle, or sine waves, not reproductions of sound effects from existing games.
3. The characters' designs do not copy the appearance (combination of hairstyle, costume, and color scheme) of any existing character.
4. None of the proper names shown on screen (place names, personal names, spell names, class names) belongs to an existing game (also avoid terms specific to a particular game, such as "勇者" (hero)).
5. No image, audio, font, or library files are bundled or fetched (the browser developer tools' Network tab shows no requests to origins other than the same origin).
