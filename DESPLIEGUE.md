# Subir el Cuadre de IVA a un VPS compartido

El VPS no es solo para esto: ahí conviven otros proyectos. Este documento asume
eso, y por eso empieza por los puertos —que es donde chocan— y no por el
`docker compose up`.

Lo de aquí está escrito para Ubuntu Server 22.04/24.04 o Debian 12. En otra
distribución cambian los comandos de `apt`, no el resto.

---

## 1. El reparto de puertos

**Esto no lo sé yo, lo tienes que mirar tú.** No tengo acceso al VPS: lo único
que he podido leer son los `docker-compose.yml` de los otros proyectos que están
en `Documents` de tu equipo. Eso dice lo que esos proyectos *declaran*, no lo que
hay levantado en el servidor, que puede ser otra cosa —otras versiones, otros
`.env`, otros puertos, o proyectos que aquí no están—.

Lo que declaran esos compose:

| Proyecto (según su compose local) | Publica             |
| ---------------------------------- | ------------------- |
| Grupo Moon                         | 80, 443, 8000, 5432 |
| CarWash                            | 3000, 3001, 5432    |
| dashboard_carpetas (IAGES)         | 8080                |
| slt-db (contenedor suelto)         | 5433                |

Por eso el Cuadre usa el **8081** y el **5434**: los dos más cercanos que no
aparecen ahí. Pero antes de levantar nada, mira lo que hay **en el VPS**:

```bash
ss -tlnp                          # que escucha ahora mismo
docker ps --format '{{.Names}}	{{.Ports}}'
```

Si el 8081 o el 5434 ya están cogidos, no hay que tocar el compose: se cambian
`CUADRE_PUERTO` y `POSTGRES_PORT` en el `.env` y ya está.

Y aunque acertara el número, el choque tampoco es lo grave. Lo que de verdad
protege es que **los dos puertos se publican solo en `127.0.0.1`**: pase lo que
pase con los vecinos, nada del Cuadre queda expuesto a internet por su cuenta.
Quien publica hacia fuera es el proxy, que es quien tiene el certificado.

> Publicar en `0.0.0.0` en un VPS no es un detalle: docker escribe sus reglas de
> `iptables` **antes** que las de `ufw`, así que un puerto publicado se ve desde
> internet aunque `ufw status` diga que está cerrado. Por eso el compose lleva
> `127.0.0.1:` delante del puerto, y por eso existe `CUADRE_ESCUCHA`.

Una cosa sí merece que la mires, porque si los compose locales se parecen a lo
desplegado, apunta a un problema que no es del Cuadre: **Grupo Moon y CarWash
declaran los dos el 5432, y hacia fuera.** Dos PostgreSQL que no pueden convivir,
y abiertos a internet. Compruébalo con el `ss -tlnp` de arriba.

---

## 2. Preparar la máquina

Si docker ya está —lo estará, si hay otros proyectos—, sáltate esto.

```bash
sudo apt update && sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Cierra la sesión y vuelve a entrar para que el grupo tenga efecto. Comprueba que
tienes compose v2, que es quien entiende el `name:` del compose:

```bash
docker compose version
```

---

## 3. Instalar el Cuadre

```bash
sudo mkdir -p /srv && cd /srv
git clone https://github.com/gestionjurisconsulta-max/cuadre-iva.git
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
el proxy del servidor. Mira primero quién tiene hoy el 80 y el 443 en el VPS:

```bash
sudo ss -tlnp 'sport = :80 or sport = :443'
```

Según lo que salga:

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

### Con nginx (vale para la a y para la b)

En `despliegue/cuadre-iva.nginx.conf` está el `server` listo:

```bash
sudo cp despliegue/cuadre-iva.nginx.conf /etc/nginx/sites-available/cuadre-iva
sudo ln -s /etc/nginx/sites-available/cuadre-iva /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d cuadre.tudominio.es
```

Si vas por la opción (b), ese mismo fichero va montado dentro del nginx que ya
tenga el 443, en lugar de en `/etc/nginx/sites-available`.

Cuando el https responda, y solo entonces:

```bash
sed -i 's/^CUADRE_COOKIE_SEGURA=0/CUADRE_COOKIE_SEGURA=1/' .env
docker compose up -d
```

---

## 5. Cortafuegos

Con todos los proyectos detrás del proxy, de fuera solo hacen falta el 22, el 80
y el 443:

```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

Y comprueba desde **otra** máquina que lo que crees cerrado lo está, porque
`ufw status` no cuenta lo que docker publica:

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
30 4 * * * root curl -fsS -X POST http://127.0.0.1:8081/api/mantenimiento/limpieza
```

`docker compose exec -T`, con la `-T`, porque desde cron no hay terminal y sin
ella el volcado sale vacío. Y el `%` va escapado: en un crontab, un `%` sin
barra corta la línea y el resto se le pasa al comando por la entrada estándar.

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
