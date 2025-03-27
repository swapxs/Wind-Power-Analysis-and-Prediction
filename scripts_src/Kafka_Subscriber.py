from pyspark.sql import SparkSession as ss
from pyspark.sql.types import (
    StructType as st,
    StructField as sf,
    StringType as srt,
    DoubleType as dt,
    LongType as lt
)

from pyspark.sql.functions import (
    from_json,
    col,
    to_date,
    to_timestamp,
    current_date,
    current_timestamp,
    lit,
    map_from_arrays,
    array,
)

sprk = ss.builder \
    .appName("KafkaSubscriber") \
    .master("spark://spark-master:7077") \
    .config(
        "spark.jars.packages", 
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.5,"
        "io.delta:delta-spark_2.12:3.3.0"
    ) \
    .config("spark.jars.repositories", "https://repos.spark-packages.org") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .config("spark.executor.cores", "4") \
    .config("spark.executor.memory", "10g")\
    .config("spark.cores.max", "4") \
    .getOrCreate()

json_schema = st([
    sf("Date/Time", srt(), True),
    sf("LV ActivePower (kW)", dt(), True),
    sf("Wind Speed (m/s)", dt(), True),
    sf("Theoretical_Power_Curve (KWh)", dt(), True),
    sf("Wind Direction (°)", dt(), True),
    sf("row_id", lt(), True)
])

kafka_df = sprk.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "xenon-topic") \
    .option("startingOffsets", "earliest") \
    .option("failOnDataLoss", "false") \
    .load()

df = kafka_df.select(
    from_json(
        col("value").cast("string"),
        json_schema
    ).alias("jsonData")
).select("jsonData.*")

final_df = df.select(
    to_date(
        to_timestamp(col("Date/Time"), "dd MM yyyy HH:mm"),
        "yyyy-MM-dd"
    ).alias("signal_date"),
    to_timestamp(col("Date/Time"), "dd MM yyyy HH:mm").alias("signal_ts"),
    current_date().alias("create_date"),
    current_timestamp().alias("create_ts"),
    map_from_arrays(
        array(
            lit("LV ActivePower (kW)"),
            lit("Wind Speed (m/s)"),
            lit("Theoretical_Power_Curve (KWh)"),
            lit("Wind Direction (°)")
        ),
        array(
            col("LV ActivePower (kW)").cast("string"),
            col("Wind Speed (m/s)").cast("string"),
            col("Theoretical_Power_Curve (KWh)").cast("string"),
            col("Wind Direction (°)").cast("string")
        )
    ).alias("signals")
)

final_df.printSchema()

final_df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/tmp/delta_kafka_subscriber_checkpoint") \
    .outputMode("append") \
    .start("/data/delta_output")

df = sprk.read.format("delta").load("/data/delta_output")
df.show(5)

sprk.stop()
