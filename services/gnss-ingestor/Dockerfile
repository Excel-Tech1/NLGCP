FROM golang:1.24-alpine AS build
WORKDIR /src
COPY services/gnss-ingestor/go.mod ./services/gnss-ingestor/
COPY services/gnss-ingestor ./services/gnss-ingestor
WORKDIR /src/services/gnss-ingestor
RUN go build -trimpath -ldflags='-s -w' -o /out/gnss-ingestor ./cmd/ingestor

FROM alpine:3.22
RUN addgroup -S nlgcp && adduser -S -G nlgcp nlgcp
COPY --from=build /out/gnss-ingestor /usr/local/bin/gnss-ingestor
USER nlgcp
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/gnss-ingestor"]
