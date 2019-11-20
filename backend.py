from math import radians, cos, sin, asin, sqrt
from flask import Flask, render_template, request,session,redirect
from flask_cors import CORS
from flask import Response
from pymongo import MongoClient
import plotly
import plotly.graph_objs as go
import matplotlib.pyplot as plt
from plotly.offline import download_plotlyjs, plot
from geopy.geocoders import Nominatim
import json
import openrouteservice
from openrouteservice.directions import directions
from openrouteservice import convert

import time 
flag = 0

api_key = "<API_KEY>" #openrouteservice api key
decoded = None
obj = None
app = Flask(__name__)
mapbox_access_token = '<MAPBOX-API-TOKEN>'
geolocator = Nominatim()
CORS(app)
mongo_client = MongoClient('localhost', 27017)
database_WT2 = mongo_client.WT2
app.secret_key = 'any random string'
car_collection = database_WT2.cars


def send_mail():
    import smtplib, ssl

    port = 587  # For starttls
    smtp_server = "smtp.gmail.com"
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.image import MIMEImage
    sender_email = "sender_email"
    receiver_email = "receiver_email"
    message = MIMEMultipart("alternative")
    message["Subject"] = "Your cab for today is here."
    message["From"] = sender_email
    fp = open('cab.png', 'rb')
    msgImage = MIMEImage(fp.read())
    fp.close()
    password = 'ikayqyrnisippuqn'

    html = """\
    <html>
    <body>
    <center>
        <h2>Greetings from Cab Booking</h2>
        <img src="cid:image1" width="25%" height="25%"></img> 
        <h4> Thank you for choosing us. Your cab is here. We hope you have a great day!!</h4>
    </center>
    
    </body>
    </html>
    """
    msgImage.add_header('Content-ID', '<image1>')
    message.attach(msgImage)
    part2 = MIMEText(html, "html")
    message.attach(part2)

    # Create secure connection with server and send email
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, password)
        for i in receiver_email:
            print(i)
            server.sendmail(sender_email, i, message.as_string())


def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians 
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula 
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles
    # print(c)
    # print(r)
    return c * r

# print(haversine(12.9581473, 77.6542132304085, 12.985588, 77.645042))

def get_cars():
    l = []
    all_cars = car_collection.find({})
    for i in all_cars:
        l.append([i['latitude'], i['longitude'], i['_id']])
    return l


def get_num_cars(lat, long, radius):
    a = get_cars()
    count = 0
    cars = []
    for i in a:
        if(haversine(lat, long, i[0], i[1])<radius):
            count+=1
            cars.append(i)
    return count, cars

def get_closest_distance(lat, long, num):
    a = get_cars()
    l1 = []
    for i in a:
        l1.append([haversine(lat, long, i[0], i[1]), i[2], [i[0], i[1]]])
    l2 = sorted(l1, key = lambda val: val[0])
    num = len(l2) if len(l2)<num else num
    min_distance = None
    answer = None
    client = openrouteservice.Client(key=api_key)
    for i in range(num):
        coords = ((l2[i][2][1], l2[i][2][0]), (long, lat))
        while(True):
            try:
                result = client.directions(coords)
                geometry = result['routes'][0]['geometry']
                break
            except Exception as e:
                print(e)
                pass
        decoded = convert.decode_polyline(geometry)
        print(decoded)
        print(result['routes'][0]['summary']['duration'])
        distance = result['routes'][0]['summary']['duration']
        if min_distance is None:
            min_distance = distance
            answer = [decoded['coordinates'], l2[i][1], [l2[i][2][0], l2[i][2][1]]]
        elif distance < min_distance:
            min_distance = distance
            answer = [decoded['coordinates'], l2[i][1], [l2[i][2][0], l2[i][2][1]]]
    print("\n")
    return answer
        

class car_state:
    def __init__(self, car_pos, line_points):
        self.index = 0
        self.car_pos = car_pos
        self.line_points = line_points
        self.segment_index = 0
        self.segment_points = []
    def move(self):
        if(self.index >= len(self.line_points)):
            return self.car_pos
        if len(self.segment_points) == 0:
            self.segment_index = 0
            tmp = self.line_points[self.index]
            latitude = tmp[0] - self.car_pos[0]
            longitutde = tmp[1] - self.car_pos[1]
            latitude_interval = latitude/5
            longitutde_interval = longitutde/5
            for i in range(1,5):
                self.segment_points.append([self.car_pos[0]+i*latitude_interval,
                self.car_pos[1]+i*longitutde_interval])
            self.segment_points.append([tmp[0], tmp[1]])
        segment_point = self.segment_points[self.segment_index]
        self.car_pos = [segment_point[0], segment_point[1]]
        self.segment_index+=1
        if(self.segment_index>=len(self.segment_points)):
            self.segment_points = []
            self.index+=1
        return self.car_pos
        

# tmp_car_pos = [12.98265, 77.63596]
# obj = car_state(tmp_car_pos, a)

def plot():
    global mapbox_access_token
    trace1 = go.Scattermapbox(lat=[12.9716],lon=[77.5946],marker={'size': 1, 'symbol': ["car"]} )
    data = [trace1]
    layout = go.Layout(
        autosize=True, showlegend=False,
        hovermode='closest',
        mapbox=go.layout.Mapbox(
            style="outdoors",
            accesstoken=mapbox_access_token,
            bearing=0,
            center=go.layout.mapbox.Center(
                lat=12.9716,
                lon=77.5946),
            pitch=0,
            zoom=12

        ))
    fig = go.Figure(data=data, layout=layout)
    fig = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return fig
def plot_cars(source, cars, route):
    global mapbox_access_token
    lats = [i[0] for i in cars]
    longs = [i[1] for i in cars]
    ids = [i[2] for i in cars]
    route_lats = [i[0] for i in route]
    route_longs = [i[1] for i in route]

    print("Number of Lats: ",len(lats))
    trace1 = go.Scattermapbox(lat=lats,lon=longs,marker={'size': 18, 'symbol': ["car" for i in range(len(lats))]}, hovertext = ids, hoverinfo = "text")
    trace2 = go.Scattermapbox(lat=[source.latitude],lon=[source.longitude],mode = "markers+text",marker={'size': 18, 'symbol': ["star"], 'color':'rgba(255, 0, 0, 1)'}, hovertext = ['Your Location'], hoverinfo = "text" )
    trace3 = go.Scattermapbox(lat=route_lats,lon=route_longs, mode = 'lines', line = {'width': 3, 'color' : 'rgba(0, 0, 255, 1)'})

    data = [trace1, trace2, trace3]
    layout = go.Layout(
        autosize=True, showlegend=False,
        hovermode='closest',
        mapbox=go.layout.Mapbox(
            style="outdoors",
            accesstoken=mapbox_access_token,
            bearing=0,
            center=go.layout.mapbox.Center(
                lat=source.latitude,
                lon=source.longitude),
            pitch=0,
            zoom=15

        ))

    fig = go.Figure(data=data, layout=layout)
    fig = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return fig
def plot_sim(obj, decoded):
    line_points_index = obj.index
    line_points = obj.line_points[line_points_index-1:]
    lati = [i[0] for i in line_points]
    long = [i[1] for i in line_points]
    lati_sd = [i[0] for i in decoded]
    long_sd = [i[1] for i in decoded]
    fig = go.Figure(go.Scattermapbox(
            lat=lati,
            lon=long,
            mode='lines'
        ))

    pos = obj.move()
    fig.add_trace(go.Scattermapbox(
            lat=[pos[0]],
            lon=[pos[1]],
            mode='markers',
            marker=go.scattermapbox.Marker(
                size=20, symbol = "car"
        ),
    ))

    fig.add_trace(go.Scattermapbox(
            lat=lati_sd,
            lon=long_sd,
            mode='lines' 
    ))


    fig.update_layout(
        autosize=True,
        hovermode=False,
        mapbox=go.layout.Mapbox(
            accesstoken=mapbox_access_token,
            bearing=0,
            center=go.layout.mapbox.Center(
                lat=obj.car_pos[0],
                lon=obj.car_pos[1]
            ),
            pitch=0,
            zoom=15
        ),
    )
    # fig.show()
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

@app.route('/login', methods=['POST'])
def login():
    req = eval(request.data)

    users = database_WT2.user

    user_doc = users.find_one({"username": req['username'], "password": req['password']})
    session['username'] = req['username']
    response = Response()
    if(user_doc!=None):
        response.status_code = 200
    else:
        response.status_code = 403
    return response

@app.route('/loadStaticMap', methods=['GET'])
def loadMap():
    return plot(), 200
@app.route('/confirm', methods=['POST'])
def confirmSim():
    print("Inside Confirm!")
    req = eval(request.data)
    coords = ((req["source_long"], req["source_lat"]),(req["dest_long"], req["dest_lat"]))

    client = openrouteservice.Client(key=api_key) # Specify your personal API key

    # decode_polyline needs the geometry only
    while(True):
        try:
            geometry = client.directions(coords)['routes'][0]['geometry']
            break
        except Exception as e:
            print(e)
            pass
    global decoded
    decoded = convert.decode_polyline(geometry)
    decoded = decoded['coordinates']
    for i in decoded:
        i[0],i[1] = i[1],i[0]
    closest_car = get_closest_distance(req['source_lat'], req['source_long'], 5);
    for i in closest_car[0]:
        i[0],i[1] = i[1],i[0]
    print(closest_car)
    global obj
    obj = car_state(closest_car[2], closest_car[0])
    return "", 200


@app.route('/logout',methods=['GET'])
def logout():
    return "hello", 200

@app.route('/search',methods=['POST'])
def search():
    req = eval(request.data)
    geolocator = Nominatim()
    while(True):
        try:
            source = geolocator.geocode(req['source'])
            dest = geolocator.geocode(req['destination'])
            break
        except:
            pass

    print(source.latitude,source.longitude)
    print(dest.latitude,dest.longitude)
    i = 0
    num_cars = 0
    print("HELLO")
    while(num_cars <= 5):
        i += 0.5
        num_cars, cars = get_num_cars(source.latitude, source.longitude, i)
    print("The Number of cars is: ", num_cars)
    coords = ((source.longitude, source.latitude),(dest.longitude, dest.latitude))

    client = openrouteservice.Client(key=api_key) # Specify your personal API key

    # decode_polyline needs the geometry only
    while(True):
        try:
            geometry = client.directions(coords)['routes'][0]['geometry']
            break
        except:
            pass

    decoded = convert.decode_polyline(geometry)
    decoded = decoded['coordinates']
    for i in decoded:
        i[0],i[1] = i[1],i[0]
    return {"source_lat": source.latitude, "source_long": source.longitude, "dest_lat": dest.latitude, "dest_long": dest.longitude, "graph":plot_cars(source, cars, decoded)}

    # return Response(status=400)
@app.route('/updateLoc', methods=['GET', 'POST'])
def updateLoc():
    while(True):
        global obj
        global decoded
        print(obj.index)
        print(len(obj.line_points)) 
        return Response(eventStream(obj, decoded), mimetype="text/event-stream")
def eventStream(obj, decoded):
    while True:
        time.sleep(1)
        print(obj.index)
        print(len(obj.line_points))
        if(obj.index >= len(obj.line_points)):
            global flag
            if(flag == 0):
                print("mail")
                send_mail()
                flag = 1
            return     
        yield "data:{}\n\n".format(plot_sim(obj, decoded))
                    
# @app.route('/moving', methods=['GET', 'POST'])
# def main():
#     while(True):
#         return Response(eventStream(), mimetype="text/event-stream")
if __name__ == '__main__':
    app.run(debug=True)