import os
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import opencage.geocoder
import pandas as pd
import plotly.graph_objs as go
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__, template_folder="templates")

OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


def build_vibe_line(description, temp_f, wind_mph, precip_chance):
    desc = (description or "").lower()
    if "thunder" in desc:
        return "Sky drama detected. Maybe admire this one from indoors."
    if "snow" in desc:
        return "It is giving winter side quest energy."
    if "rain" in desc or precip_chance >= 60:
        return "Bring an umbrella. Main character energy does not block rain."
    if temp_f >= 95:
        return "Hot enough to question all life choices outside."
    if temp_f <= 35:
        return "Cold enough that your coffee needs emotional support."
    if wind_mph >= 20:
        return "Wind is in a chaotic mood right now."
    return "Weather is mostly cooperative. Proceed with confidence."


def build_activity_hint(temp_f, wind_mph, precip_chance):
    if precip_chance >= 65:
        return "Plan: indoor plans win today."
    if temp_f >= 88:
        return "Plan: shade, water, and minimal heroics."
    if temp_f <= 40:
        return "Plan: layers first, ambition second."
    if wind_mph >= 18:
        return "Plan: secure hats and loose opinions."
    return "Plan: great window for a walk, patio, or quick errand run."


@app.route("/")
@app.route("/weather")
def weather():
    if not request.args.get("lat") or not request.args.get("lon"):
        return render_template("weather.html")

    lat = request.args.get("lat")
    lon = request.args.get("lon")

    try:
        forecast_url = (
            "https://api.openweathermap.org/data/2.5/forecast"
            f"?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=imperial"
        )
        forecast_resp = requests.get(forecast_url, timeout=10).json()

        current_url = (
            "https://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=imperial"
        )
        current_resp = requests.get(current_url, timeout=10).json()

        temperature = current_resp["main"]["temp"]
        feels_like = current_resp["main"].get("feels_like", temperature)
        humidity_now = current_resp["main"].get("humidity", 0)
        wind_now = current_resp.get("wind", {}).get("speed", 0)
        description = current_resp["weather"][0]["description"]
        current_weather = (
            f"The current temperature is {temperature}\N{DEGREE SIGN}F and the weather is {description}."
        )

        city = None
        state = None
        try:
            geocoder = opencage.geocoder.OpenCageGeocode(OPENCAGE_API_KEY)
            result = geocoder.reverse_geocode(float(lat), float(lon))
            if result:
                components = result[0].get("components", {})
                city = components.get("city") or components.get("town") or components.get(
                    "village"
                )
                state = components.get("state")
        except Exception as e:
            print(f"Geocoding failed: {e}")

        tz_offset_sec = current_resp.get("timezone", 0)
        tz = dt_timezone(timedelta(seconds=tz_offset_sec))

        hourly_forecast = []
        for forecast in forecast_resp["list"]:
            utc_dt = datetime.fromtimestamp(forecast["dt"], tz=dt_timezone.utc)
            local_dt = utc_dt.astimezone(tz)
            pop = round(forecast.get("pop", 0) * 100)
            rain_3h = forecast.get("rain", {}).get("3h", 0)
            snow_3h = forecast.get("snow", {}).get("3h", 0)
            hourly_forecast.append(
                {
                    "datetime": local_dt.replace(tzinfo=None),
                    "temperature": forecast["main"]["temp"],
                    "humidity": forecast["main"]["humidity"],
                    "wind_speed": forecast["wind"]["speed"],
                    "pop": pop,
                    "rain_mm": rain_3h,
                    "snow_mm": snow_3h,
                    "description": forecast["weather"][0]["description"],
                    "icon": forecast["weather"][0]["icon"],
                }
            )

        df = pd.DataFrame(hourly_forecast)

        df["date"] = df["datetime"].dt.date
        daily_summary = []
        for date, group in df.groupby("date"):
            day_name = group["datetime"].iloc[0].strftime("%A")
            hi = round(group["temperature"].max())
            lo = round(group["temperature"].min())
            max_pop = group["pop"].max()
            avg_wind = round(group["wind_speed"].mean())
            desc_counts = group["description"].value_counts()
            dominant_desc = desc_counts.index[0]
            summary = f"{day_name}: {hi}\N{DEGREE SIGN}/{lo}\N{DEGREE SIGN} - {dominant_desc.title()}"
            if max_pop > 0:
                summary += f", {max_pop}% chance of precip"
            if avg_wind >= 10:
                summary += f", wind {avg_wind} mph"
            daily_summary.append(summary)
        forecast_text = daily_summary
        today_group = list(df.groupby("date"))[0][1]
        today_hi = round(today_group["temperature"].max())
        today_lo = round(today_group["temperature"].min())
        max_pop_next_day = int(df.head(8)["pop"].max())

        hourly_tiles = []
        for _, row in df.head(8).iterrows():
            hourly_tiles.append(
                {
                    "time": row["datetime"].strftime("%I %p").lstrip("0"),
                    "temp": round(row["temperature"]),
                    "pop": int(row["pop"]),
                    "desc": row["description"].title(),
                    "icon_url": f"https://openweathermap.org/img/wn/{row['icon']}@2x.png",
                }
            )

        sunrise_str = None
        sunset_str = None
        sunrise_time = None
        sunset_time = None
        try:
            sr_ts = current_resp["sys"]["sunrise"]
            ss_ts = current_resp["sys"]["sunset"]
            sr_dt = datetime.fromtimestamp(sr_ts, tz=dt_timezone.utc).astimezone(tz)
            ss_dt = datetime.fromtimestamp(ss_ts, tz=dt_timezone.utc).astimezone(tz)
            sunrise_time = sr_dt.time().replace(tzinfo=None)
            sunset_time = ss_dt.time().replace(tzinfo=None)
            sunrise_str = "Sunrise: " + sr_dt.strftime("%I:%M %p")
            sunset_str = "Sunset: " + ss_dt.strftime("%I:%M %p")
        except Exception as e:
            print(f"Sunrise/sunset calculation failed: {e}")

        night_rects = []
        if sunrise_time and sunset_time:
            df["daytime"] = df["datetime"].apply(
                lambda x: "day" if sunrise_time < x.time() <= sunset_time else "night"
            )
            for _, row in df[df["daytime"] == "night"].iterrows():
                night_rects.append(
                    {
                        "type": "rect",
                        "xref": "x",
                        "yref": "paper",
                        "x0": row["datetime"],
                        "y0": 0,
                        "x1": row["datetime"] + pd.Timedelta(hours=3),
                        "y1": 1,
                        "fillcolor": "rgba(100,101,102,0.5)",
                        "line": {"width": 0},
                        "layer": "below",
                    }
                )

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df["datetime"],
                y=df["temperature"],
                name="Temperature",
                yaxis="y",
                mode="lines+markers",
                marker=dict(size=5),
                line=dict(width=2.5, color="#A67458"),
                hovertemplate="<b>%{x|%b %d %I:%M %p}</b><br>Temp: %{y:.0f}\N{DEGREE SIGN}F<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df["datetime"],
                y=df["humidity"],
                name="Humidity",
                yaxis="y2",
                mode="lines+markers",
                marker=dict(size=5),
                line=dict(width=2.5, color="#3E848C"),
                hovertemplate="Humidity: %{y}%<extra></extra>",
            )
        )
        fig.add_trace(
            go.Bar(
                x=df["datetime"],
                y=df["pop"],
                name="Precip %",
                yaxis="y2",
                marker=dict(color="rgba(100, 149, 237, 0.35)"),
                width=3 * 3600 * 1000,
                hovertemplate="Precip: %{y}%<extra></extra>",
            )
        )
        if night_rects:
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    marker=dict(
                        symbol="square", color="rgba(100,101,102,0.5)", size=10
                    ),
                    name="Night",
                )
            )

        temp_min = max(0, int(df["temperature"].min() // 10) * 10 - 10)
        temp_max = int(df["temperature"].max() // 10) * 10 + 20
        temp_ticks = list(range(temp_min, temp_max + 1, 10))
        tick_vals = pd.date_range(
            start=df["datetime"].min(), end=df["datetime"].max(), freq="12h"
        )

        fig.update_layout(
            hovermode="x",
            hoverlabel=dict(
                bgcolor="rgba(30,30,30,0.9)",
                font_color="white",
                bordercolor="rgba(80,80,80,0.5)",
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white", size=12),
            showlegend=True,
            shapes=night_rects,
            yaxis=dict(
                color="white",
                showgrid=False,
                zeroline=False,
                tickvals=temp_ticks,
                ticktext=[f"{v}\N{DEGREE SIGN}F" for v in temp_ticks],
                range=[temp_min, temp_max],
            ),
            yaxis2=dict(
                overlaying="y",
                side="right",
                color="white",
                showgrid=False,
                zeroline=False,
                ticksuffix="%",
                range=[0, 100],
            ),
            xaxis=dict(
                color="white",
                showgrid=False,
                zeroline=False,
                tickvals=tick_vals,
                tickformat="%b %d\n%I %p",
                tickangle=0,
                tickfont=dict(size=11),
                range=[df["datetime"].min(), df["datetime"].max()],
            ),
            autosize=True,
            bargap=0,
            margin=dict(l=50, r=50, t=10, b=60),
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5
            ),
        )

        plot = fig.to_html(full_html=False, config={"displayModeBar": False})
        location_name = None
        if city and state:
            location_name = f"{city}, {state}"
        elif city:
            location_name = city
        else:
            location_name = f"{float(lat):.2f}, {float(lon):.2f}"

        vibe_line = build_vibe_line(description, temperature, wind_now, max_pop_next_day)
        activity_hint = build_activity_hint(temperature, wind_now, max_pop_next_day)

        return render_template(
            "weather.html",
            current_weather=current_weather,
            city=city,
            state=state,
            location_name=location_name,
            sunrise=sunrise_str,
            sunset=sunset_str,
            plot=plot,
            forecast_text=forecast_text,
            current_temp=round(temperature),
            feels_like=round(feels_like),
            humidity_now=round(humidity_now),
            wind_now=round(wind_now),
            today_hi=today_hi,
            today_lo=today_lo,
            max_pop_next_day=max_pop_next_day,
            hourly_tiles=hourly_tiles,
            vibe_line=vibe_line,
            activity_hint=activity_hint,
            local_generated_at=datetime.now(tz).strftime("%I:%M %p"),
        )

    except Exception as e:
        print(f"Weather route error: {e}")
        return render_template(
            "weather.html", error_msg=f"Could not load weather data: {e}"
        )


@app.route("/search_location", methods=["GET"])
def search_location():
    query = request.args.get("query")
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    url = (
        "https://api.opencagedata.com/geocode/v1/json"
        f"?q={query}&key={OPENCAGE_API_KEY}&limit=10"
    )
    response = requests.get(url, timeout=5)
    data = response.json()

    locations = []
    seen = set()
    for result in data.get("results", []):
        comp = result.get("components", {})
        city = comp.get("city") or comp.get("town") or comp.get("village", "")
        state = comp.get("state", "")
        country = comp.get("country", "")
        lat = result["geometry"]["lat"]
        lon = result["geometry"]["lng"]

        if city and country:
            label = f"{city}, {state}" if state else f"{city}, {country}"
            if label not in seen:
                seen.add(label)
                locations.append({"name": label, "lat": lat, "lon": lon})

    return jsonify(locations[:5])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
