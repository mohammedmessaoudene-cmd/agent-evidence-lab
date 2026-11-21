package corpusreaders

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

// Run the native decoder and decision function on the same files as Python.
func TestP04FinalHoldProbe(t *testing.T) {
	dir := os.Getenv("P04_RECORDS")
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		data, err := os.ReadFile(filepath.Join(dir, entry.Name()))
		if err != nil {
			t.Fatal(err)
		}
		value, err := ebDecode(data)
		if err != nil {
			t.Fatal(err)
		}
		result := ebDecide(value.(ebObj))
		line, err := json.Marshal(map[string]string{
			"case": entry.Name(), "decision": result.Decision, "reason": result.Reason,
		})
		if err != nil {
			t.Fatal(err)
		}
		fmt.Println("P04_RECORD", string(line))
	}
	corpus, err := Judge(os.Getenv("P04_CORPUS"))
	if err != nil {
		t.Fatal(err)
	}
	if !corpus.OK() {
		t.Fatalf("corpus findings: %v %v", corpus.Findings, corpus.Members)
	}
	fmt.Println("P04_CORPUS", len(corpus.Members))
}
