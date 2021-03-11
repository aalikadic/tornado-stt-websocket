import json
import queue
import threading
from tornado import websocket, web, ioloop, httpserver
from google.cloud import speech
#from google.cloud import logging
import nest_asyncio
import os
import configparser
import re
#from google.cloud.speech_v1 import enums

config_file = configparser.ConfigParser()
config_file.read('config.ini')

API = str(config_file.get('api','name'))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = API

#logger = logging.Client().logger("speech-poc")
nest_asyncio.apply()


class IndexHandler(web.RequestHandler):
  def get(self):
    self.render("index.html")


class AudioWebSocket(websocket.WebSocketHandler):
  def check_origin(self, origin):
    return True

  def open(self):
    self.transcoder = None
    print("WebSocket opened")

  def on_message(self, message):
    if self.transcoder is None:
      config = json.loads(message)
      print(config)
      print('on_message')

      self.transcoder = Transcoder(
        sample_rate=config["sampleRateHz"],
        language_code=config["language"])
 
      # Start the transcoding of audio to text 
      self.transcoder.start()
    else:
      
      self.transcoder.write(message)
      interim_results = self.transcoder.interim_results()
      
      if None not in interim_results and len(interim_results) != 0:
          print(interim_results)
          # logger.log_struct({
          #     "request": "/translate",
          #     "interim_results": interim_results})
          self.write_message(json.dumps(interim_results))
      
      
          

  def on_close(self):
    self.transcoder.stop()
    self.transcoder = None
    print("WebSocket closed")


class AudioStream(object):
  """An iteratable object which holds audio data that is pending processing."""

  def __init__(self):
    self.buff = queue.Queue()
    self.closed = False

  def __iter__(self):
    return self

  def __next__(self):
    return self.next()

  def write(self, data):
    self.buff.put(data)

  def close(self):
    self.closed = True
    self.buff.queue.clear()

  def next(self):
    while not self.closed:
      chunk = self.buff.get()
      if chunk is not None:
        return chunk
    raise StopIteration


class Transcoder(object):
  """Coordinates the translation of a raw audio stream."""

  def __init__(self, sample_rate, language_code,
                             encoding=speech. RecognitionConfig.AudioEncoding.LINEAR16):
    self.sample_rate = sample_rate
    self.language_code = 'sr-RS'
    self.encoding = encoding
    self.closed = True
    self.audio = AudioStream()
    self.result_queue = queue.Queue()


  def write(self, data):
    """Write a chunk of audio to be translated."""
    self.audio.write(data)

  def start(self):
    """Start transcribing audio."""
    self.closed = False
    thread = threading.Thread(target=self._process)
    thread.start()

  def stop(self):
    """Stop transcribing audio."""
    self.closed = True
    self.audio.close()

  def _process(self):
    """Handles the setup of transcription request, and retreving audio chunks in queue."""
    client = speech.SpeechClient()

    config = speech.RecognitionConfig(
        encoding=self.encoding,
        sample_rate_hertz=self.sample_rate,
        language_code=self.language_code)
    
    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True)

    # Give it a config and a generator which procduces audio chunks. in return
    # you get an iterator of results
    responses = client.streaming_recognize(streaming_config, self.generator())
    
    # This will block until there's no more interim translation results left
    for response in responses:
      self.result_queue.put(self._response_to_dict(response))

  def _response_to_dict(self, response):
    """Converts a response from streaming api to python dict."""
    # if response is None:
    #   return []

    #output = []
    for result in response.results:
      #r = {}
      transcript = result.alternatives[0].transcript
      # r["transcript"] = transcript
      # r["stability"] = result.stability
      # r["is_final"] = result.is_final

      if result.is_final:
          return transcript
      # r["alternatives"] = []
      # for alt in result.alternatives:
      #   r["alternatives"].append({
      #       "transcript": alt.transcript,
      #       "confidence": alt.confidence,
      #   })
      
      
      if re.search(r"\b(izlaz|kraj)\b", transcript, re.I):
          #print("Ovo je transcript" + transcript)
          #print("Ovo je overwrite_chars" + overwrite_chars)
          print("Izlaz..")
          self.stop()
          print(self.closed)
          #self.transcoder = None
          #return output
          #print(test[1])
          #break
      
      
    #return output

  def interim_results(self, max_results=10):
    """Grabs interm results from the queue."""
    results = []
    while len(results) < max_results and not self.result_queue.empty():
      try:
        result = self.result_queue.get(block=False)
      except queue.QueueEmpty:
        return results
      results.append(result)
    return results

  def generator(self):
    """Generator that yields audio chunks."""
    for chunk in self.audio:
      yield speech.StreamingRecognizeRequest(audio_content=chunk)

 
app = web.Application([
    (r"/", IndexHandler),
    (r"/index.html", IndexHandler),
    (r"/translate", AudioWebSocket),
])

if __name__ == "__main__":
  # ssl_options = {
  #     "certfile":  "tls/server.cert",
  #     "keyfile": "tls/server.key",
  # }
  
  nest_asyncio.apply()
  server = httpserver.HTTPServer(
      app, xheaders=True)
  server.listen(8002, address='127.0.0.1')
  #ioloop.IOLoop.current().start()