import collections
import hashlib
import hmac
import time

"""
Example showing API Signature calculation
for an API call to the /v2/current/{station-id}
API endpoint

starting: sudo python3 ./davis_api_toolc.py
"""

apikey = "????????????????????????????????"  #REPLACE THIS WITH YOUR API KEY
apisecret = "????????????????????????????????" #REPLACE THIS WITH YOUR API SECRET
stationid = "99999" #REPLACE THIS WITH YOUR STATION ID for History and Current data

"""
Here is the list of parameters we will use for this example.
"""

parameters = {
  "api-key":apikey,
  "api-secret":apisecret,
  "t":int(time.time())
}

parametersh = {
  "api-key":apikey,
  "api-secret":apisecret, 
  "end-timestamp":int(time.time()),
  "start-timestamp":int(time.time() - 360),
  "station-id":stationid,
  "t":int(time.time())
}

parametersc = {
  "api-key":apikey,
  "api-secret":apisecret,
  "station-id":stationid,
  "t":int(time.time())
}

"""
Now we will compute the API Signature.
The signature process uses HMAC SHA-256 hashing and we will
use the API Secret as the hash secret key. That means that
right before we calculate the API Signature we will need to
remove the API Secret from the list of parameters given to
the hashing algorithm.
"""

"""
First we need to sort the paramters in ASCII order by the key.
The parameter names are all in US English so basic ASCII sorting is
safe. We will use an ordered dictionary to help keep the
parameters sorted.
"""
parameters = collections.OrderedDict(sorted(parameters.items()))
parametersh = collections.OrderedDict(sorted(parametersh.items()))

"""
Let's take a moment to print out all parameters for debugging
and educational purposes.
"""
for key in parameters:
  print("Parameter name: \"{}\" has value \"{}\"".format(key, parameters[key]))

"""
Save and remove the API Secret from the set of parameters.
"""
apiSecret = parameters["api-secret"];
parameters.pop("api-secret", None);

apiSecret0 = parametersc["api-secret"];
parametersc.pop("api-secret", None);

apiSecret1 = parametersh["api-secret"];
parametersh.pop("api-secret", None);


"""
Iterate over the remaining sorted parameters and concatenate
the parameter names and values into a single string.
"""
data = ""
for key in parameters:
  data = data + key + str(parameters[key])

data0 = ""
for key in parametersc:
 data0 = data0 + key + str(parametersc[key])

data1 = ""
for key in parametersh:
 data1 = data1 + key + str(parametersh[key])

"""
Let's print out the data we are going to hash.
"""
print("Data string to hash is: \"{}\"".format(data))

"""
Calculate the HMAC SHA-256 hash that will be used as the API Signature.
"""
apiSignature = hmac.new(
  apiSecret.encode('utf-8'),
  data.encode('utf-8'),
  hashlib.sha256
).hexdigest()

apiSignature0 = hmac.new(
  apiSecret0.encode('utf-8'),
  data0.encode('utf-8'),
  hashlib.sha256
).hexdigest()

apiSignature1 = hmac.new(
  apiSecret1.encode('utf-8'),
  data1.encode('utf-8'),
  hashlib.sha256
).hexdigest()


"""
Let's see what the final API Signature looks like.
"""
print("API Signature is: \"{}\"".format(apiSignature))
print("API Signature history is: \"{}\"".format(apiSignature1))
print(" ")
"""
Now that the API Signature is calculated let's see what the final
v2 API URL would look like for this scenario.
"""
print("v2 API URL: Stations")
print("https://api.weatherlink.com/v2/stations?api-key={}&api-signature={}&t={}".format(parameters["api-key"], apiSignature, parameters["t"]))
print(" ")
#
print("v2 API URL: Current")
print("https://api.weatherlink.com/v2/current/{}?api-key={}&api-signature={}&t={}".format(parametersc["station-id"], parametersc["api-key"], apiSignature0, parametersc["t"]))
print(" ")
#
print("v2 API URL: Historic")
print("https://api.weatherlink.com/v2/historic/{}?api-key={}&start-timestamp={}&end-timestamp={}&api-signature={}&t={}".format(parametersh["station-id"], parametersh["api-key"], parametersh["start-timestamp"], parametersh["end-timestamp"], apiSignature1, parametersh["t"] ) )
