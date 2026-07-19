Creado:
	`/etc/systemd/system/pelis-feed-web.service`

Install & Run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pelis-feed-web
sudo systemctl status pelis-feed-web
curl -s http://127.0.0.1:8080/api/health   # sanity check, from the server itself
```

Checking why curl is not giving an answer:

```bash
sudo ss -tlnp | grep 8080
sudo iptables -L INPUT -v -n --line-numbers
```

iptables:

```
Chain INPUT (policy ACCEPT 0 packets, 0 bytes)
num   pkts bytes target     prot opt in     out     source               destination         
1     231M   37G ACCEPT     all  --  lo     *       0.0.0.0/0            0.0.0.0/0           
2        0     0 REJECT     all  --  *      *       0.0.0.0/0            127.0.0.0/8          reject-with icmp-port-unreachable
3     396M  130G ACCEPT     all  --  *      *       0.0.0.0/0            0.0.0.0/0            state RELATED,ESTABLISHED
4    6384K  332M ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:80
5      92M 4921M ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:443
6     146K 8447K ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:993
7     365K   20M ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:25
8     177K   10M ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:2525
9    6502K  387M ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            state NEW tcp dpt:22
10   2129K  120M ACCEPT     icmp --  *      *       0.0.0.0/0            0.0.0.0/0           
11      40  2937 ACCEPT     udp  --  *      *       0.0.0.0/0            0.0.0.0/0            udp dpt:51820
12   3395K  193M LOG        all  --  *      *       0.0.0.0/0            0.0.0.0/0            limit: avg 5/min burst 5 LOG flags 0 level 7 prefix "iptables denied: "
13   8906K  527M DROP       all  --  *      *       0.0.0.0/0            0.0.0.0/0           
```

Problemas con la base: 

```
sqlalchemy.exc.OperationalError: (pymysql.err.OperationalError) (1071, 'Specified key was too long; max key length is 3072 bytes') 
```

Explicación:

```
The error is MySQL rejecting the schema.
The cause: you have UNIQUE (torrent_url) on a VARCHAR(1000) column.
If the table uses utf8mb4 (4 bytes per character, which is the modern MySQL default), that's 1000 × 4 = 4000 bytes — over InnoDB's 3072-byte limit for a single index key.
```

Fixing by code, hashing the URL and make that unique instead (most robust for long/variable-length URLs).
This is usually the best pattern for URLs, since URLs can be arbitrarily long and you don't want to keep shrinking a VARCHAR.

Then I have to rebuild the DB:

```
CREATE DATABASE rssfeeds CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
DROP DATABASE rssfeeds;
```
