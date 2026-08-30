// AgentPack's Windows stdio-to-HTTP MCP bridge.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Set at build time by AgentPack. A source-hash revision lets a newer MCPB
// coexist with an already-running bridge instead of overwriting it on Windows.
var bridgeVersion = "dev"

type headers []string

func (h *headers) String() string         { return strings.Join(*h, ", ") }
func (h *headers) Set(value string) error { *h = append(*h, value); return nil }

type headerTransport struct{ headers http.Header }

func (t headerTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	clone := req.Clone(req.Context())
	for key, values := range t.headers {
		for _, value := range values {
			clone.Header.Add(key, value)
		}
	}
	return http.DefaultTransport.RoundTrip(clone)
}

func installAndRestart() error {
	local := os.Getenv("LOCALAPPDATA")
	if local == "" {
		return fmt.Errorf("LOCALAPPDATA is not set")
	}
	source, err := os.Executable()
	if err != nil {
		return err
	}
	target := filepath.Join(local, "AgentPack", "bridge", bridgeVersion, "agentpack-http-bridge.exe")
	if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
		return err
	}
	if source != target {
		// Do not replace an already running bridge. Multiple Claude sessions can
		// start at once; a completed bridge is immutable for this version.
		if _, err := os.Stat(target); err == nil {
			return restartInstalled(target)
		} else if !os.IsNotExist(err) {
			return err
		}

		in, err := os.Open(source)
		if err != nil {
			return err
		}
		defer in.Close()
		temporary := target + "." + fmt.Sprint(os.Getpid()) + ".new"
		out, err := os.Create(temporary)
		if err != nil {
			return err
		}
		if _, err = io.Copy(out, in); err != nil {
			out.Close()
			os.Remove(temporary)
			return err
		}
		if err = out.Close(); err != nil {
			os.Remove(temporary)
			return err
		}
		if err = os.Rename(temporary, target); err != nil {
			os.Remove(temporary)
			// Another session completed the same version while this one copied it.
			if _, statErr := os.Stat(target); statErr != nil {
				return err
			}
		}
	}
	return restartInstalled(target)
}

func restartInstalled(target string) error {
	args := append(os.Args[1:], "--installed")
	cmd := exec.Command(target, args...)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	return cmd.Run()
}

func main() {
	var endpoint string
	var installed bool
	var values headers
	flag.StringVar(&endpoint, "url", "", "HTTP MCP endpoint")
	flag.Var(&values, "header", "HTTP header, e.g. Authorization: Bearer token")
	flag.BoolVar(&installed, "installed", false, "internal")
	flag.Parse()
	if endpoint == "" {
		fmt.Fprintln(os.Stderr, "--url is required")
		os.Exit(2)
	}
	if !installed {
		if err := installAndRestart(); err != nil {
			var exitErr *exec.ExitError
			if errors.As(err, &exitErr) {
				// The installed bridge reached the remote server but failed later.
				// Preserve that exit code without incorrectly calling it an install error.
				os.Exit(exitErr.ExitCode())
			}
			fmt.Fprintln(os.Stderr, "AgentPack bridge install:", err)
			os.Exit(1)
		}
		return
	}
	headers := http.Header{}
	for _, value := range values {
		key, val, ok := strings.Cut(value, ":")
		if !ok || strings.TrimSpace(key) == "" {
			fmt.Fprintln(os.Stderr, "invalid --header")
			os.Exit(2)
		}
		headers.Add(strings.TrimSpace(key), strings.TrimSpace(val))
	}
	ctx := context.Background()
	client := mcp.NewClient(&mcp.Implementation{Name: "agentpack-http-bridge", Version: bridgeVersion}, nil)
	session, err := client.Connect(ctx, &mcp.StreamableClientTransport{Endpoint: endpoint, HTTPClient: &http.Client{Transport: headerTransport{headers}}}, nil)
	if err != nil {
		fmt.Fprintln(os.Stderr, "HTTP MCP connection:", err)
		os.Exit(1)
	}
	defer session.Close()
	listed, err := session.ListTools(ctx, nil)
	if err != nil {
		fmt.Fprintln(os.Stderr, "HTTP MCP tools/list:", err)
		os.Exit(1)
	}
	server := mcp.NewServer(&mcp.Implementation{Name: "agentpack-http-proxy", Version: bridgeVersion}, nil)
	for _, remote := range listed.Tools {
		tool := *remote
		mcp.AddTool(server, &tool, func(ctx context.Context, req *mcp.CallToolRequest, raw json.RawMessage) (*mcp.CallToolResult, any, error) {
			result, err := session.CallTool(ctx, &mcp.CallToolParams{Name: req.Params.Name, Arguments: raw})
			return result, nil, err
		})
	}
	if err := server.Run(ctx, &mcp.StdioTransport{}); err != nil {
		fmt.Fprintln(os.Stderr, "stdio MCP:", err)
		os.Exit(1)
	}
}
