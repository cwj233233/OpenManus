import argparse
import asyncio

from app.agent.manus import Manus
from app.logger import logger


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, help="Input prompt for the agent")
    args = parser.parse_args()
    agent = await Manus.create()
    try:
        prompt = args.prompt or input("Enter your prompt: ").strip()
        if not prompt:
            logger.warning("Empty prompt provided.")
            return
        logger.warning("Processing your request...")
        await agent.run(prompt)
        logger.info("Request processing completed.")
    except KeyboardInterrupt:
        logger.warning("Operation interrupted.")
    finally:
        await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
