#!/usr/bin/env python3
"""
piSynapse — Memory Pipeline Debug Script
Run: python debug_test.py
Does not require pytest or external dependencies.
"""

import asyncio
import sys
import re
import os

# Assumes execution from the project root
sys.path.insert(0, os.path.dirname(__file__))

PASS = "\033[0;32m  ✅ PASS\033[0m"
FAIL = "\033[0;31m  ❌ FAIL\033[0m"
INFO = "\033[0;34m  ℹ \033[0m"

passed = 0
failed = 0

def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"{PASS}  {label}")
    else:
        failed += 1
        print(f"{FAIL}  {label}")
        if detail:
            print(f"       → {detail}")

# ─────────────────────────────────────────────────────────────
# BLOCK 1: extract_and_clean_memory — pure Python, no async
# ─────────────────────────────────────────────────────────────
print("\n\033[0;34m══ 1. extract_and_clean_memory ══\033[0m")

# Try importing the function; otherwise test with our own copy
try:
    from routers.chat import extract_and_clean_memory
    print(f"{INFO} imported from routers/chat.py")
except ImportError:
    try:
        from chat import extract_and_clean_memory
        print(f"{INFO} imported from chat.py")
    except ImportError:
        print(f"\033[0;31m  ❌ extract_and_clean_memory could not be imported — function missing!\033[0m")
        extract_and_clean_memory = None

if extract_and_clean_memory is None:
    # If the function does not exist, define it inline and show it
    print("     Expected function:\n")
    print("""
     def extract_and_clean_memory(reply_text: str) -> tuple[str, list]:
         memories_to_save = []
         cleaned_lines = []
         pattern = re.compile(r"^MEMORY:\\s*\\[(.*?)\\]\\s*(.+)$", re.IGNORECASE)
         for line in reply_text.splitlines():
             match = pattern.match(line.strip())
             if match:
                 memories_to_save.append((match.group(1).strip(), match.group(2).strip()))
             else:
                 cleaned_lines.append(line)
         return "\\n".join(cleaned_lines).strip(), memories_to_save
    """)
    failed += 1
else:
    # Test 1: Normal MEMORY line
    reply1 = "Hello John!\n\nMEMORY: [personal] Name is John and from Istanbul."
    cleaned1, mems1 = extract_and_clean_memory(reply1)
    check("Normal MEMORY line is extracted", len(mems1) == 1,
          f"Expected 1 memory, found: {len(mems1)} | mems={mems1}")
    check("MEMORY line is removed from cleaned reply",
          "MEMORY:" not in cleaned1,
          f"cleaned={repr(cleaned1)}")
    check("Category parsed correctly",
          mems1[0][0] == "personal" if mems1 else False,
          f"mems={mems1}")

    # Test 2: No MEMORY line — should remain untouched
    reply2 = "The weather is nice today."
    cleaned2, mems2 = extract_and_clean_memory(reply2)
    check("Reply without MEMORY line passes unchanged",
          cleaned2 == "The weather is nice today." and len(mems2) == 0,
          f"cleaned={repr(cleaned2)}, mems={mems2}")

    # Test 3: Multiple MEMORY lines
    reply3 = "Okay!\nMEMORY: [preference] Likes Python\nMEMORY: [work] Working on a Raspberry Pi project"
    cleaned3, mems3 = extract_and_clean_memory(reply3)
    check("Multiple MEMORY lines are extracted",
          len(mems3) == 2,
          f"Expected 2, found: {len(mems3)} | mems={mems3}")

    # Test 4: Simulate actual model output
    real_output = (
        "Hello John, nice to meet you! "
        "I'm glad to learn that you're from Istanbul. "
        "How can I help you today?\n\n"
        "MEMORY: [personal] Name is John and from Istanbul."
    )
    cleaned4, mems4 = extract_and_clean_memory(real_output)
    check("MEMORY extracted from real model output",
          len(mems4) == 1,
          f"mems={mems4}")
    check("Real model output cleaned successfully",
          "MEMORY:" not in cleaned4,
          f"cleaned={repr(cleaned4)}")

# ─────────────────────────────────────────────────────────────
# BLOCK 2: embedding.py — can the model be loaded?
# ─────────────────────────────────────────────────────────────
print("\n\033[0;34m══ 2. Embedding ══\033[0m")

try:
    from embedding import embed, cosine_similarity
    print(f"{INFO} embedding.py imported")

    vec1 = embed("User's name is John")
    check("embed() returns bytes", isinstance(vec1, bytes) and len(vec1) > 0,
          f"type={type(vec1)}, len={len(vec1)}")

    vec2 = embed("The user is named John")
    score_similar = cosine_similarity(vec1, vec2)
    check("Semantically similar sentences get a high score (>0.7)",
          score_similar > 0.7,
          f"score={score_similar:.3f}")

    vec3 = embed("The weather is very nice and warm today")
    score_different = cosine_similarity(vec1, vec3)
    check("Semantically different sentences get a low score (<0.7)",
          score_different < 0.7,
          f"score={score_different:.3f}")

    check("None input safely returns 0.0",
          cosine_similarity(None, vec1) == 0.0)

except Exception as e:
    failed += 1
    print(f"\033[0;31m  ❌ Embedding import/runtime error: {e}\033[0m")

# ─────────────────────────────────────────────────────────────
# BLOCK 3: memory.py — async DB operations
# ─────────────────────────────────────────────────────────────
print("\n\033[0;34m══ 3. Memory DB (async) ══\033[0m")

# Temporary path for test DB
os.environ["DB_PATH"] = "/tmp/pisynapse_debug_test.db"

async def run_memory_tests():
    global passed, failed
    try:
        from memory import init_db, save_memory, get_all_memories, find_similar_memory, clear_history

        await init_db()
        check("init_db() runs without errors", True)

        # save_memory
        await save_memory("User's name is John", category="personal", user_id="debug_user")
        mems = await get_all_memories("debug_user")
        check("save_memory() stores data",
              any("John" in m["content"] for m in mems),
              f"DB contents: {mems}")

        # Semantic deduplication
        await save_memory("The user is named John", category="personal", user_id="debug_user")
        mems2 = await get_all_memories("debug_user")
        check("Semantic duplicate is not stored (deduplication)",
              len(mems2) == len(mems),
              f"Before: {len(mems)}, After: {len(mems2)} — duplicate was stored!")

        # Different content should be stored
        await save_memory("The user develops software with Python", category="work", user_id="debug_user")
        mems3 = await get_all_memories("debug_user")
        check("Different content is stored successfully",
              len(mems3) > len(mems2),
              f"Before: {len(mems2)}, After: {len(mems3)}")

    except Exception as e:
        failed += 1
        print(f"\033[0;31m  ❌ Memory test error: {e}\033[0m")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up test DB
        if os.path.exists("/tmp/pisynapse_debug_test.db"):
            os.remove("/tmp/pisynapse_debug_test.db")

asyncio.run(run_memory_tests())

# ─────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────
total = passed + failed
print(f"\n\033[0;34m══ Result: {passed}/{total} tests passed ══\033[0m")

if failed == 0:
    print("\033[0;32m  All tests passed. Pipeline is healthy.\033[0m\n")
    sys.exit(0)
else:
    print(f"\033[0;31m  {failed} tests failed. Check the FAIL lines above.\033[0m\n")
    sys.exit(1)