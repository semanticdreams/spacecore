(local fs (require :fs))

(fn resolve-chunk-bytes [opts]
  (if (and opts (not= opts.chunk-bytes nil))
      opts.chunk-bytes
      65536))

(fn file [path opts]
  (local absolute-path (fs.absolute path))
  (local token (fs.file-token absolute-path))
  (local read-range
    (fn [_self offset max-bytes]
      (fs.read-byte-range absolute-path offset max-bytes)))
  (local current-token
    (fn [_self]
      (fs.file-token absolute-path)))
  (local refresh-token
    (fn [source]
      (local next-token (source:current-token))
      (set source.baseline-token next-token)
      (set source.size next-token.size)
      next-token))
  {:path absolute-path
   :baseline-token token
   :size token.size
   :chunk-bytes (resolve-chunk-bytes opts)
   :read-range read-range
   :current-token current-token
   :refresh-token refresh-token})

;; Read-only in-memory source for display-only buffers (run payloads, reports).
;; The token is stable for the lifetime of the text; a new snapshot is a new
;; source, which keeps baseline/size semantics honest without file IO.
(fn string-source [text opts]
  (assert (= (type text) :string) "lazy-text-source.string requires string text")
  (local token {:size (length text) :memory true})
  (fn read-range [_self offset max-bytes]
    (assert (and (= (type offset) :number) (>= offset 0))
            "lazy-text-source.string read-range requires numeric offset")
    (assert (and (= (type max-bytes) :number) (> max-bytes 0))
            "lazy-text-source.string read-range requires positive max-bytes")
    (local finish (math.min (length text) (+ offset max-bytes)))
    (if (> finish offset)
        {:bytes (string.sub text (+ offset 1) finish)
         :offset offset
         :bytes-read (- finish offset)}
        {:bytes "" :offset offset :bytes-read 0}))
  {:path nil
   :baseline-token token
   :size token.size
   :chunk-bytes (resolve-chunk-bytes opts)
   :read-range read-range
   :current-token (fn [_self] token)
   :refresh-token (fn [self]
                    (set self.baseline-token token)
                    (set self.size token.size)
                    token)})

{:file file :string string-source}
