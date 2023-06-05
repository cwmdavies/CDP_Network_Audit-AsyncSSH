from random import random
import asyncio

IP_Addresses = [
    "192.168.1.1",
    "192.168.1.2",
    "192.168.1.3",
    "192.168.1.4",
]


# coroutine to generate work
async def producer(queue):
    print('Producer: Running')
    # generate work
    for ip in IP_Addresses:
        # generate a value
        value = random()
        # block to simulate work
        await asyncio.sleep(value)
        # add to the queue
        await queue.put(ip)
    print('Producer: Done')


# coroutine to consume work
async def consumer(queue):
    print('Consumer: Running')
    # consume work
    while True:
        # generate a value
        value = random()
        # get a unit of work
        item = await queue.get()
        # report
        print(f'>got item: {item}')
        # block while processing
        if item:
            await asyncio.sleep(value)
        # mark the task as done
        queue.task_done()


# entry point coroutine
async def main():
    # create the shared queue
    queue = asyncio.Queue()
    # start the consumer
    _ = asyncio.create_task(consumer(queue))
    # start the producer and wait for it to finish
    await asyncio.create_task(producer(queue))
    # wait for all items to be processed
    await queue.join()


# start the asyncio program
asyncio.run(main())
