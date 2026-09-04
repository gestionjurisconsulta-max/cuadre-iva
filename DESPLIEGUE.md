# Subir el Cuadre de IVA a un VPS compartido

El VPS no es solo para esto: ahí conviven otros proyectos. Este documento asume
eso, y por eso empieza por los puertos —que es donde chocan— y no por el
`docker compose up`.

Hay dos familias de comandos según la distribución, y **no son intercambiables**
en las partes que tocan nginx, el cortafuegos y SELinux:

- **Rocky / AlmaLinux / RHEL** — `dnf`, vhosts en `/etc/nginx/conf.d/`,
  `firewalld`, y **SELinux**, que tiene su propia opinión sobre si nginx puede
  hablar con el contenedor.
- **Ubuntu / Debian** — `apt`, vhosts en `sites-available` + `sites-enabled`,
  `ufw`, sin SELinux.

Donde cambian, van los dos.

---

## 1. El reparto de puertos

Esto es lo que había en el servidor cuando se escribió esto (`rocky-32gb-hel1-1`,
un Hetzner con Rocky Linux). **Vuélvelo a mirar antes de levantar nada**, porque
cambia sin avisar:

```bash
sudo ss -tlnp
```

Lo que salió:

| Puerto            | Quién           | Alcance          |
| ----------------- | --------------- | ---------------- |
| 22                | sshd            | internet         |
| **80, 443**       | **nginx del sistema** | internet   |
| 3000              | docker          | **internet**     |
| 21115–21119       | docker (RustDesk) | internet       |
| 3005, 3011, 5000, 8001, **8080** | docker | solo loopback |
| 5439              | docker (PostgreSQL) | solo loopback |
| —                 | tailscaled      | la VPN           |

Tres cosas que salen de ahí:

- **El 8081 y el 5434 están libres**, que son justo los que trae el `.env.example`.
  No hay que cambiar nada. El 8080 estaba cogido, como se sospechaba.
- **Ya hay un nginx del sistema** con el 80 y el 443, y **no está en un
  contenedor**. Eso resuelve el punto 4: es el proxy, y al Cuadre solo hay que
  añadirle un `server` más. No hay que tocar el compose de ningún otro proyecto.
- Los demás proyectos ya publican en loopback y salen por ese nginx. El Cuadre
  hace lo mismo, así que encaja sin pelearse con nadie.

Lo único que desentona es el **3000 en `0.0.0.0`**: es el único servicio de
aplicación que se salta el proxy y se planta en internet por http. No es del
Cuadre y no hace falta tocarlo para desplegarlo, pero mereces saberlo. Los
21115–21119 también están abiertos, pero esos son de RustDesk y tienen que
estarlo para que el escritorio remoto funcione.

> Que el Cuadre publique en `127.0.0.1` no es una manía: docker escribe sus reglas
> de `iptables` **antes** que las de `firewalld`, así que un puerto publicado en
> `0.0.0.0` se ve desde internet aunque el cortafuegos diga que está cerrado. Es
> exactamente lo que le pasa hoy al 3000.

Si algún día el 8081 o el 5434 aparecen ocupados, no se toca el compose: se
cambian `CUADRE_PUERTO` y `POSTGRES_PORT` en el `.env` y ya está.

---

## 2. Preparar la máquina

Si en el `ss` del punto 1 salían procesos `docker-proxy`, docker ya está y solo
hay que confirmar que el compose es el v2, que es quien entiende el `name:`:

```bash
docker compose version
```

Si no estuviera, en Rocky/RHEL:

```bash
sudo dnf install -y dnf-plugins-core git
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
```

Y en Ubuntu/Debian:

```bash
sudo apt update && sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
```

---

## 3. Instalar el Cuadre

### La llave de despliegue

**El repositorio es privado**, así que un `git clone` por https no va a poder.
El servidor necesita una llave propia —no la tuya— y de solo lectura:

```bash
ssh-keygen -t ed25519 -C "vps-cuadre-iva" -f ~/.ssh/cuadre_iva -N ""
cat ~/.ssh/cuadre_iva.pub
```

Esa línea se pega en GitHub, en el repositorio `cuadre-iva`:
**Settings › Deploy keys › Add deploy key**. **Sin** marcar *Allow write access*:
el servidor solo tiene que leer, y una llave de despliegue robada que además
escriba es una vía para colar código en el repositorio.

```bash
printf 'Host github-cuadre
  HostName github.com
  User git
  IdentityFile ~/.ssh/cuadre_iva
  IdentitiesOnly yes
' >> ~/.ssh/config
ssh -T git@github-cuadre
```

Tiene que contestar con el nombre del repositorio y un *does not provide shell
access*. Eso es lo correcto: significa que la llave vale y que no da más.

### Clonar

```bash
sudo mkdir -p /srv && cd /srv
git clone github-cuadre:gestionjurisconsulta-max/cuadre-iva.git
cd cuadre-iva
cp .env.example .env
```

Ahora edita el `.env`. Lo que hay que cambiar sí o sí está marcado con `VPS:`
dentro del propio fichero:

```ini
POSTGRES_PASSWORD=<pon aquí lo que saque: openssl rand -base64 30>
CUADRE_COOKIE_SEGURA=1
CUADRE_SOCIEDADES_FICHERO=/srv/cuadre-iva/mis_empresas.json
CUADRE_TRABAJADORES=2
```

`CUADRE_COOKIE_SEGURA=1` solo funciona si delante hay https de verdad. Puesto a
1 sin TLS, nadie podrá iniciar sesión y el fallo no dice por qué: el navegador
descarta la cookie en silencio. Si aún no has hecho el punto 4, déjalo a 0 y
cámbialo después.

La lista de sociedades lleva NIF de clientes y **no va en el repositorio**. Se
copia a mano y se monta en solo lectura:

```bash
scp mis_empresas.json usuario@vps:/srv/cuadre-iva/mis_empresas.json
```

El formato está en `mis_empresas.example.json`. Sin ese fichero la aplicación
funciona igual: solo pierde el aviso de que el NIF de una sociedad vuestra se ha
colado en el número de factura.

Levantar y crear el primer usuario:

```bash
docker compose up -d --build
docker compose ps
docker compose exec api python gestion_usuarios.py crear ana "Ana Perez"
curl -sS http://127.0.0.1:8081/api/salud
```

`docker compose ps` tiene que enseñar los tres servicios en `healthy`.

**Comprueba que la lista de sociedades es la buena**, porque si no lo es no te
vas a enterar: cuando `CUADRE_SOCIEDADES_FICHERO` se queda sin tocar, el compose
monta `mis_empresas.example.json` y la aplicación arranca igual de contenta.

```bash
docker compose exec -T api python -c "import json;print(len(json.load(open('/datos/mis_empresas.json'))),'sociedades')"
```

Si dice **3**, es el ejemplo. Se arregla apuntando bien la ruta y recreando:

```bash
sed -i 's#^CUADRE_SOCIEDADES_FICHERO=.*#CUADRE_SOCIEDADES_FICHERO=/srv/cuadre-iva/mis_empresas.json#' .env && docker compose up -d
```

Y de paso, que la contraseña de la base no se haya quedado en la de por defecto
—pasa si el `.env` se editó mal, y tampoco lo dice nadie—:

```bash
docker compose exec -T api sh -c 'case "$CUADRE_BD" in *:cuadre@*) echo "OJO: contrasena por defecto";; *) echo "contrasena propia OK";; esac'
```

`crear` **pide la contraseña por teclado** y la hace repetir; no se pasa como
argumento a propósito, porque un argumento queda en el historial del shell y en
la lista de procesos. Por eso el `exec` va **sin `-T`**: sin terminal, `getpass`
revienta y el mensaje que sale habla de la base de datos, que no es el problema.

No hay pantalla de administración ni permisos: las cuentas se crean aquí, en el
servidor, y quien entra lo ve todo. Las demás órdenes son `listar`, `clave`,
`activar` y `desactivar`.

---

## 4. Ponerle un dominio y TLS

El Cuadre escucha en `127.0.0.1:8081` y no tiene certificado. Quien lo publica es
el proxy del servidor, y en este VPS **ese proxy ya existe**: el nginx del
sistema que tiene el 80 y el 443, fuera de docker, por el que ya salen los
demás proyectos. Así que no hay que instalar nada ni mover puertos de nadie:
solo añadirle un `server` más y sacarle el certificado. Vete directo a **Con
nginx**, aquí abajo.

Comprueba antes que sigue siendo así:

```bash
sudo ss -tlnp 'sport = :80 or sport = :443'
```

Lo de Caddy solo aplicaría si algún día ese nginx desapareciera y el 80/443
quedaran libres. Los dos caminos son:

**a) Nadie los tiene, o hay un nginx/Caddy del sistema.** El camino limpio:
el proxy del sistema se queda el 80/443 y cada proyecto publica solo en
loopback, como este. Si algún otro proyecto los tiene cogidos desde su propio
compose, hay que moverlo a loopback también.

**b) Los tiene el nginx de otro proyecto** —por lo que declara su compose,
Grupo Moon es el candidato—. Se le añade un `server` más y listo: no hay que
tocar los puertos de nadie, pero deja la puerta de entrada del servidor dentro
del proyecto de otro, que es un sitio raro para tenerla.

Es una decisión de infraestructura, no del Cuadre: los dos caminos funcionan y el
Cuadre no cambia en ninguno.

### Con Caddy (opción a — saca y renueva el certificado solo)

```bash
sudo apt install -y caddy
```

En `/etc/caddy/Caddyfile`:

```
cuadre.tudominio.es {
    request_body {
        max_size 200MB
    }
    reverse_proxy 127.0.0.1:8081
}
```

```bash
sudo systemctl reload caddy
```

El `max_size` tiene que coincidir con `CUADRE_MAX_SUBIDA_MB`, o cortará la
subida antes de que la aplicación pueda decir nada.

### Con nginx (es lo que hay en el VPS)

**El orden importa**: el vhost definitivo lleva dos `ssl_certificate` apuntando
a ficheros que todavía no existen, y nginx no arranca así. Primero un `server`
del 80 mínimo, luego el certificado, y al final el fichero bueno.

**Dónde se copia depende de la distribución**, y es el error más fácil de
cometer: en Rocky no existe `sites-available`, y un fichero dejado ahí no lo lee
nadie ni da ningún error —el dominio simplemente no responde—. En Rocky va en
`/etc/nginx/conf.d/*.conf`, que se incluye entero y solo; en Ubuntu/Debian, en
`sites-available` con el enlace en `sites-enabled`.

Antes de nada, que el DNS resuelva ya, o certbot no podrá validar:

```bash
dig +short auditoria.iages.es
```

#### 1. Un server del 80, provisional

```bash
cat > /etc/nginx/conf.d/cuadre-iva.conf <<'EOF'
server {
    listen 80;
    server_name auditoria.iages.es;
    location / { proxy_pass http://127.0.0.1:8081; proxy_set_header Host $host; }
}
EOF
nginx -t && systemctl reload nginx
```

```bash
curl -sS -o /dev/null -w '%{http_code}
' http://auditoria.iages.es/
```

Un `200` confirma que nginx alcanza el contenedor. Si sale **502**, mira lo de
SELinux aquí abajo antes de seguir.

#### 2. El certificado

En Rocky/RHEL certbot vive en EPEL:

```bash
dnf install -y epel-release && dnf install -y certbot python3-certbot-nginx
```

```bash
certbot certonly --nginx -d auditoria.iages.es
```

`certonly` y no `--nginx` a secas: así certbot saca el certificado y **no toca**
la configuración, que la escribimos nosotros en el paso siguiente.

#### 3. El vhost de verdad

```bash
cp /srv/cuadre-iva/despliegue/cuadre-iva.nginx.conf /etc/nginx/conf.d/cuadre-iva.conf
nginx -t && systemctl reload nginx
```

Ese fichero ya lleva el dominio, el TLS, los timeouts y el
`client_max_body_size` cuadrado con `CUADRE_MAX_SUBIDA_MB`. Si lo reaprovechas
para otra instalación, el dominio sale en cuatro sitios.

#### SELinux, en Rocky y AlmaLinux

Con SELinux en *enforcing* **nginx no puede abrir una conexión de red por su
cuenta**, ni siquiera al 127.0.0.1 de la propia máquina. El síntoma es un **502
Bad Gateway** con `Permission denied` en `/var/log/nginx/error.log`, y despista
mucho: el contenedor está sano, el `curl` directo al 8081 funciona, y aun así
el navegador da 502.

```bash
getenforce
```

Si dice `Enforcing`:

```bash
setsebool -P httpd_can_network_connect 1
```

En este VPS salió `Permissive`, así que no hizo falta. Si algún día se pone en
enforcing —que sería lo suyo—, esto pasa a ser obligatorio.

---

## 5. Cortafuegos

Con todos los proyectos detrás del proxy, de fuera solo hacen falta el 22, el 80
y el 443:

Rocky / RHEL usa firewalld:

```bash
sudo firewall-cmd --permanent --add-service=ssh --add-service=http --add-service=https && sudo firewall-cmd --reload
```

Ubuntu / Debian usa ufw:

```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

Y comprueba desde **otra** máquina que lo que crees cerrado lo está, porque ni
`ufw status` ni `firewall-cmd --list-all` cuentan lo que docker publica: docker
escribe sus propias reglas y se salta las dos cosas.

```bash
nmap -Pn -p 3000,3001,5432,5433,5434,8000,8080,8081 <ip-del-vps>
```

Del Cuadre —el 8081 y el 5434— no debe aparecer nada. Si aparece algún 5432,
eso es un PostgreSQL de otro proyecto abierto a internet, y toca cerrarlo.

---

## 6. Copias de seguridad

El histórico está en el volumen `cuadre-iva_datos_cuadre`. Los libros subidos se
borran solos a los `CUADRE_RETENCION_DIAS` días; lo que hay que guardar es la
base.

En `/etc/cron.d/cuadre-iva`:

```cron
# Copia diaria a las 3:15; se guardan 14 dias.
15 3 * * * root cd /srv/cuadre-iva && docker compose exec -T db pg_dump -U cuadre cuadre | gzip > /var/backups/cuadre-$(date +\%F).sql.gz
20 3 * * * root find /var/backups -name 'cuadre-*.sql.gz' -mtime +14 -delete
# La limpieza de cuadres viejos corre al arrancar la API; esto la fuerza a diario.
30 4 * * * root cd /srv/cuadre-iva && docker compose exec -T api python -c "from cuadre import trabajos; print(trabajos.limpia())"
```

`docker compose exec -T`, con la `-T`, porque desde cron no hay terminal y sin
ella el volcado sale vacío. Y el `%` va escapado: en un crontab, un `%` sin
barra corta la línea y el resto se le pasa al comando por la entrada estándar.

La limpieza va por `exec` y **no** por `curl` al endpoint
`/api/mantenimiento/limpieza`: ese endpoint exige sesión, y desde cron no hay
cookie que valga. Un `curl` ahí contesta **401** y no borra nada, y como el
fallo es silencioso los libros de los clientes se quedarían en el servidor
mucho más allá de `CUADRE_RETENCION_DIAS`. El endpoint sigue existiendo para
lanzarla a mano desde la aplicación, con la sesión puesta.

Que está limpiando de verdad se comprueba mirando lo que imprime: sale un
`{'borrados': N, 'recuperados': M}`. Si en vez de eso sale un error de la base,
la línea no está haciendo nada.

Restaurar:

```bash
gunzip -c /var/backups/cuadre-2026-09-02.sql.gz | docker compose exec -T db psql -U cuadre cuadre
```

Prueba la restauración una vez, en local. Una copia que no se ha restaurado
nunca no se sabe si es una copia.

---

## 7. Actualizar

```bash
cd /srv/cuadre-iva
git pull
docker compose up -d --build
docker compose logs -f api
```

Se reconstruye solo lo que ha cambiado. La base no se toca y el histórico se
queda donde está.

---

## 8. Qué mirar cuando algo falla

```bash
docker compose ps
docker compose logs -f api
docker stats --no-stream
```

- **La interfaz carga pero no deja entrar.** Casi siempre es
  `CUADRE_COOKIE_SEGURA=1` sin https delante: el navegador tira la cookie sin
  avisar.
- **Un cuadre grande se corta a mitad.** Los timeouts del proxy de delante.
  `web/nginx.conf` ya usa 300 s; el de fuera tiene que darle al menos lo mismo.
- **«Request Entity Too Large» al subir libros.** El `client_max_body_size` de
  nginx —o el `max_size` de Caddy— del proxy de delante, que tiene que coincidir
  con `CUADRE_MAX_SUBIDA_MB`.
- **El VPS va lento cuando alguien cuadra.** Cada cuadre se come una CPU entera
  durante unos 30 s y la máquina es compartida. Baja `CUADRE_TRABAJADORES`.
- **El histórico aparece vacío después de mover la carpeta.** El nombre del
  proyecto está clavado en el compose (`name: cuadre-iva`) precisamente para que
  eso no pase. Si pasa, comprueba con `docker volume ls` que sigue existiendo
  `cuadre-iva_datos_cuadre`.
